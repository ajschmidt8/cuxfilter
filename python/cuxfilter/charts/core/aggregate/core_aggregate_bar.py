import panel as pn
import dask_cudf
import numpy as np

from .core_aggregate import BaseAggregateChart
from ....assets.numba_kernels import calc_groupby, calc_value_counts
from ....layouts import chart_view


class BaseBar(BaseAggregateChart):
    reset_event = None
    _datatile_loaded_state: bool = False
    filter_widget = None
    use_data_tiles = True
    datatile_active_color = "#8ab4f7"

    @property
    def datatile_loaded_state(self):
        return self._datatile_loaded_state

    @datatile_loaded_state.setter
    def datatile_loaded_state(self, state: bool):
        self._datatile_loaded_state = state
        if self.add_interaction:
            if state:
                self.filter_widget.bar_color = self.datatile_active_color
            else:
                self.filter_widget.bar_color = "#d3d9e2"

    def __init__(
        self,
        x,
        y=None,
        data_points=None,
        add_interaction=True,
        aggregate_fn="count",
        width=400,
        height=400,
        step_size=None,
        step_size_type=int,
        title="",
        autoscaling=True,
        **library_specific_params,
    ):
        """
        Description:

        -------------------------------------------
        Input:
            x
            y
            data_points
            add_interaction
            aggregate_fn
            width
            height
            step_size
            step_size_type
            title
            autoscaling
            x_label_map
            y_label_map
            **library_specific_params
        -------------------------------------------

        Ouput:

        """
        self.x = x
        self.y = y
        self.stride = step_size
        self.stride_type = step_size_type
        self.data_points = data_points
        self.add_interaction = add_interaction
        self.aggregate_fn = aggregate_fn
        self.height = height
        self.width = width
        if len(title) == 0:
            self.title = self.x
        else:
            self.title = title
        self.autoscaling = autoscaling
        self.library_specific_params = library_specific_params

    def initiate_chart(self, dashboard_cls):
        """
        Description:

        -------------------------------------------
        Input:
        data: cudf DataFrame
        -------------------------------------------

        Ouput:

        """
        if dashboard_cls._cuxfilter_df.data[self.x].dtype == "bool":
            self.min_value = 0
            self.max_value = 1
            self.stride = 1
            # set axis labels:
            dict_map = {0: "False", 1: "True"}
            if len(self.x_label_map) == 0:
                self.x_label_map = dict_map
            if (
                self.y != self.x
                and self.y is not None
                and len(self.y_label_map) == 0
            ):
                self.y_label_map = dict_map
        else:
            if (
                type(dashboard_cls._cuxfilter_df.data)
                == dask_cudf.core.DataFrame
            ):
                self.min_value = (
                    dashboard_cls._cuxfilter_df.data[self.x].min().compute()
                )
                self.max_value = (
                    dashboard_cls._cuxfilter_df.data[self.x].max().compute()
                )
            else:
                self.min_value = dashboard_cls._cuxfilter_df.data[self.x].min()
                self.max_value = dashboard_cls._cuxfilter_df.data[self.x].max()

            if self.max_value < 1 and self.stride_type == int:
                self.stride_type = float

            if self.stride is None and self.data_points is not None:
                if self.stride_type == int:
                    self.stride = int(
                        round(
                            (self.max_value - self.min_value)
                            / self.data_points
                        )
                    )
                else:
                    self.stride = float(
                        (self.max_value - self.min_value) / self.data_points
                    )

        if self.stride is None:
            # No stride for bins specified, in this we case,
            # we compute cudf.Series.value_counts() for histogram
            self.custom_binning = False
        else:
            self.custom_binning = True

        self.calculate_source(dashboard_cls._cuxfilter_df.data)
        self.generate_chart()
        self.apply_mappers()

        if self.add_interaction:
            self.add_range_slider_filter(dashboard_cls)
        self.add_events(dashboard_cls)

    def view(self):
        return chart_view(self.chart, self.filter_widget, width=self.width)

    def calculate_source(self, data, patch_update=False):
        """
        Description:

        -------------------------------------------
        Input:

        -------------------------------------------

        Ouput:
        """
        if self.y == self.x or self.y is None:
            # it's a histogram
            df, self.data_points = calc_value_counts(
                data[self.x], self.stride, self.min_value, self.data_points,
                self.custom_binning
            )
            if self.data_points > 50_000:
                print(
                    "number of x-values for a bar chart ",
                    "exceeds 50,000 points.",
                    "Performance may be laggy, its recommended ",
                    "to use custom data_points parameter to ",
                    "enforce custom binning for smooth crossfiltering",
                )
        else:
            self.aggregate_fn = "mean"
            df = calc_groupby(self, data)
            if self.data_points is None:
                self.data_points = len(df[0])

        if self.stride is None:
            self.stride = self.stride_type(
                round((self.max_value - self.min_value) / self.data_points)
            )

        if self.custom_binning:
            if len(self.x_label_map) == 0:
                temp_mapper_index = np.array(df[0])
                temp_mapper_value = np.round(
                    (temp_mapper_index * self.stride) + self.min_value, 4,
                ).astype("str")
                temp_mapper_index = temp_mapper_index.astype("str")
                self.x_label_map = dict(
                    zip(temp_mapper_index, temp_mapper_value)
                )
        dict_temp = {
            "X": df[0],
            "Y": df[1],
        }
        if (
            patch_update and
            len(dict_temp["X"]) < len(self.source.data[self.data_x_axis])
        ):
            # if not all X axis bins are provided, filling bins not updated
            # with zeros
            y_axis_data = self._compute_array_all_bins(
                self.source.data[self.data_x_axis],
                self.source.data[self.data_y_axis],
                dict_temp["X"],
                dict_temp["Y"]
            )

            dict_temp = {
                "X": self.source.data[self.data_x_axis],
                "Y": y_axis_data,
            }

        self.format_source_data(dict_temp, patch_update)

    def add_range_slider_filter(self, dashboard_cls):
        """
        Description: add range slider to the bottom of the chart,
                    for the filter function to facilitate interaction behavior,
                    that updates the rest of the charts on the page,
                    using datatiles
        -------------------------------------------
        Input:

        -------------------------------------------

        Ouput:
        """
        if self.stride is None:
            self.stride = self.stride_type(
                round((self.max_value - self.min_value) / self.data_points)
            )

        self.filter_widget = pn.widgets.RangeSlider(
            start=self.min_value,
            end=self.max_value,
            value=(self.min_value, self.max_value),
            step=self.stride,
            **{"width": self.width},
            sizing_mode="scale_width",
        )

        def filter_widget_callback(event):
            if dashboard_cls._active_view != self.name:
                dashboard_cls._reset_current_view(new_active_view=self)
                dashboard_cls._calc_data_tiles()

            dashboard_cls._query_datatiles_by_range(event.new)

        # add callback to filter_Widget on value change
        self.filter_widget.param.watch(
            filter_widget_callback, ["value"], onlychanged=False
        )

    def compute_query_dict(self, query_str_dict):
        """
        Description:

        -------------------------------------------
        Input:
        query_dict = reference to dashboard.__cls__.query_dict
        -------------------------------------------

        Ouput:
        """

        if self.filter_widget.value != (
            self.filter_widget.start,
            self.filter_widget.end,
        ):
            min_temp, max_temp = self.filter_widget.value
            query = (
                str(self.stride_type(round(min_temp, 4)))
                + "<="
                + str(self.x)
                + "<="
                + str(self.stride_type(round(max_temp, 4)))
            )
            query_str_dict[self.name] = query
        else:
            query_str_dict.pop(self.name, None)

    def add_events(self, dashboard_cls):
        """
        Description:

        -------------------------------------------
        Input:

        -------------------------------------------

        Ouput:
        """
        if self.reset_event is not None:
            self.add_reset_event(dashboard_cls)

    def add_reset_event(self, dashboard_cls):
        """
        Description:

        -------------------------------------------
        Input:

        -------------------------------------------

        Ouput:
        """

        def reset_callback(event):
            self.filter_widget.value = (
                self.filter_widget.start,
                self.filter_widget.end,
            )

        # add callback to reset chart button
        self.add_event(self.reset_event, reset_callback)
