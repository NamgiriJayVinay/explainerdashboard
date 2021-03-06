__all__ = [
    'PredictionSummaryComponent',
    'ImportancesComponent',
    'PdpComponent',
]

import dash
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_table

from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from .dashboard_methods import *

class PredictionSummaryComponent(ExplainerComponent):
    def __init__(self, explainer, title="Prediction Summary",
                    header_mode="none", name=None,
                    hide_index=False, hide_percentile=False,
                    index=None, percentile=True):
        """Shows a summary for a particular prediction

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Prediction Summary".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_index (bool, optional): hide index selector. Defaults to False.
            hide_percentile (bool, optional): hide percentile toggle. Defaults to False.
            index ({int, str}, optional): Index to display prediction summary for. Defaults to None.
            percentile (bool, optional): Whether to add the prediction percentile. Defaults to True.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_index, self.hide_percentile = hide_index, hide_percentile
        self.index, self.percentile = index, percentile

        self.index_name = 'modelprediction-index-'+self.name

    def _layout(self):
        return html.Div([
            html.H3("Predictions summary:"),
            dbc.Row([
                make_hideable(
                    dbc.Col([
                        dbc.Label("Index:"),
                        dcc.Dropdown(id='modelprediction-index-'+self.name, 
                                options = [{'label': str(idx), 'value':idx} 
                                                for idx in self.explainer.idxs],
                                value=self.index)
                    ], md=8), hide=self.hide_index),
                make_hideable(
                    dbc.Col([
                        dbc.Label("Show Percentile:"),
                        dbc.FormGroup(
                        [
                            dbc.RadioButton(
                                id='modelprediction-percentile-'+self.name, 
                                className="form-check-input",
                                checked=self.percentile),
                            dbc.Label("Show percentile",
                                    html_for='modelprediction-percentile'+self.name, 
                                    className="form-check-label"),
                        ], check=True)
                    ], md=4), hide=self.hide_percentile),
            ]),
            dbc.Row([
                dbc.Col([
                    dcc.Loading(id='loading-modelprediction-'+self.name, 
                         children=[dcc.Markdown(id='modelprediction-'+self.name)]),    
                ], md=12)
            ])
        ])

    def _register_callbacks(self, app):
        @app.callback(
            Output('modelprediction-'+self.name, 'children'),
            [Input('modelprediction-index-'+self.name, 'value'),
             Input('modelprediction-percentile-'+self.name, 'checked'),
             Input('pos-label', 'value')])
        def update_output_div(index, include_percentile, pos_label):
            if index is not None:
                return self.explainer.prediction_result_markdown(index, include_percentile=include_percentile, pos_label=pos_label)
            raise PreventUpdate


class ImportancesComponent(ExplainerComponent):
    def __init__(self, explainer, title="Importances",
                        header_mode="none", name=None,
                        hide_type=False, hide_depth=False, hide_cats=False,
                        importance_type="shap", depth=None, cats=True):
        """Display features importances component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Importances".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_type (bool, optional): Hide permutation/shap selector toggle. 
                        Defaults to False.
            hide_depth (bool, optional): Hide number of features toggle. 
                        Defaults to False.
            hide_cats (bool, optional): Hide group cats toggle. 
                        Defaults to False.
            importance_type (str, {'permuation', 'shap'} optional): 
                        initial importance type to display. Defaults to "shap".
            depth (int, optional): Initial number of top features to display. 
                        Defaults to None (=show all).
            cats (bool, optional): Group categoricals. Defaults to True.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_type = hide_type
        self.hide_depth = hide_depth
        self.hide_cats = hide_cats
        if self.explainer.cats is None or not self.explainer.cats:
            self.hide_cats = True

        assert importance_type in ['shap', 'permutation'], \
            "importance type must be either 'shap' or 'permutation'!"
        self.importance_type = importance_type
        if depth is not None:
            depth = min(depth, len(explainer.columns_ranked_by_shap(cats)))
        self.depth = depth
        self.cats = cats
        self.register_dependencies(['shap_values', 'shap_values_cats',
            'permutation_importances', 'permutation_importances_cats'])

    def _layout(self):
        return dbc.Container([
            dbc.Row([dbc.Col([html.H2('Feature Importances:')])]),
            dbc.Row([
                make_hideable(
                    dbc.Col([
                        dbc.FormGroup([
                            dbc.Label("Importances type:"),
                            dbc.RadioItems(
                                options=[
                                    {'label': 'Permutation Importances', 
                                    'value': 'permutation'},
                                    {'label': 'SHAP values', 
                                    'value': 'shap'}
                                ],
                                value=self.importance_type,
                                id='importances-permutation-or-shap-'+self.name,
                                inline=True,
                            ),
                        ]),
                    ]), self.hide_type),
                make_hideable(
                    dbc.Col([
                        html.Label('Depth:'),
                        dcc.Dropdown(id='importances-depth-'+self.name,
                                            options = [{'label': str(i+1), 'value':i+1} 
                                                        for i in range(self.explainer.n_features(self.cats))],
                                            value=self.depth)
                    ]), self.hide_depth),
                make_hideable(
                    dbc.Col([
                        dbc.Label("Grouping:"),
                        dbc.FormGroup(
                        [
                            dbc.RadioButton(
                                id='importances-group-cats-'+self.name, 
                                className="form-check-input",
                                checked=self.cats),
                            dbc.Label("Group Cats",
                                    html_for='importances-group-cats-'+self.name,
                                    className="form-check-label"),
                        ], check=True), 
                    ]),  self.hide_cats),        
            ], form=True),

            dbc.Row([
                dbc.Col([
                    dcc.Loading(id='loading-importances-graph-'+self.name, 
                            children=[dcc.Graph(id='importances-graph-'+self.name)])
                ]),
            ]), 
            ], fluid=True)
        
    def _register_callbacks(self, app, **kwargs):
        @app.callback(  
            Output('importances-graph-'+self.name, 'figure'),
            [Input('importances-depth-'+self.name, 'value'),
             Input('importances-group-cats-'+self.name, 'checked'),
             Input('importances-permutation-or-shap-'+self.name, 'value'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')]
        )
        def update_importances(depth, cats, permutation_shap, pos_label, tab): 
            return self.explainer.plot_importances(
                        kind=permutation_shap, topx=depth, 
                        cats=cats, pos_label=pos_label)


class PdpComponent(ExplainerComponent):
    def __init__(self, explainer, title="Partial Dependence Plot",
                    header_mode="none", name=None,
                    hide_col=False, hide_index=False, hide_cats=False,
                    hide_dropna=False, hide_sample=False, 
                    hide_gridlines=False, hide_gridpoints=False,
                    col=None, index=None, cats=True,
                    dropna=True, sample=100, gridlines=50, gridpoints=10):
        """Show Partial Dependence Plot component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Partial Dependence Plot".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_col (bool, optional): Hide feature selector. Defaults to False.
            hide_index (bool, optional): Hide index selector. Defaults to False.
            hide_cats (bool, optional): Hide group cats toggle. Defaults to False.
            hide_dropna (bool, optional): Hide drop na's toggle Defaults to False.
            hide_sample (bool, optional): Hide sample size input. Defaults to False.
            hide_gridlines (bool, optional): Hide gridlines input. Defaults to False.
            hide_gridpoints (bool, optional): Hide gridpounts input. Defaults to False.
            col (str, optional): Feature to display PDP for. Defaults to None.
            index ({int, str}, optional): Index to add ice line to plot. Defaults to None.
            cats (bool, optional): Group categoricals for feature selector. Defaults to True.
            dropna (bool, optional): Drop rows where values equal explainer.na_fill (usually -999). Defaults to True.
            sample (int, optional): Sample size to calculate average partial dependence. Defaults to 100.
            gridlines (int, optional): Number of ice lines to display in plot. Defaults to 50.
            gridpoints (int, optional): Number of breakpoints on horizontal axis Defaults to 10.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_col, self.hide_index, self.hide_cats = hide_col, hide_index, hide_cats
        self.hide_dropna, self.hide_sample = hide_dropna, hide_sample
        self.hide_gridlines, self.hide_gridpoints = hide_gridlines, hide_gridpoints

        self.col, self.index, self.cats = col, index, cats
        self.dropna, self.sample, self.gridlines, self.gridpoints = \
            dropna, sample, gridlines, gridpoints

        self.index_name = 'pdp-index-'+self.name

        if self.col is None:
            self.col = self.explainer.columns_ranked_by_shap(self.cats)[0]

    def _layout(self):
        return html.Div([
                html.H3('Partial Dependence Plot:'),
                dbc.Row([
                    make_hideable(
                        dbc.Col([
                            dbc.Label("Feature:", html_for='pdp-col'),
                            dcc.Dropdown(id='pdp-col-'+self.name, 
                                options=[{'label': col, 'value':col} 
                                            for col in self.explainer.columns_ranked_by_shap(self.cats)],
                                value=self.col),
                        ], md=4), hide=self.hide_col),
                    make_hideable(
                        dbc.Col([
                            dbc.Label("Index:"),
                            dcc.Dropdown(id='pdp-index-'+self.name, 
                                options = [{'label': str(idx), 'value':idx} 
                                                for idx in self.explainer.idxs],
                                value=None)
                        ], md=4), hide=self.hide_index), 
                    make_hideable(
                        dbc.Col([
                            dbc.Label("Grouping:"),
                            dbc.FormGroup(
                            [
                                dbc.RadioButton(
                                    id='pdp-group-cats-'+self.name, 
                                    className="form-check-input",
                                    checked=self.cats),
                                dbc.Label("Group Cats",
                                        html_for='pdp-group-cats-'+self.name, 
                                        className="form-check-label"),
                            ], check=True)
                        ], md=3), hide=self.hide_cats),
                ], form=True),
                dbc.Row([
                    dbc.Col([
                        dcc.Loading(id='loading-pdp-graph-'+self.name, 
                            children=[dcc.Graph(id='pdp-graph-'+self.name)]),
                    ])
                ]),
                dbc.Row([
                    make_hideable(
                        dbc.Col([ #
                            dbc.Label("Drop na:"),
                                dbc.FormGroup(
                                [
                                    dbc.RadioButton(
                                        id='pdp-dropna-'+self.name, 
                                        className="form-check-input",
                                        checked=self.dropna),
                                    dbc.Label("Drop na's",
                                            html_for='pdp-dropna-'+self.name, 
                                            className="form-check-label"),
                                ], check=True)
                        ]), hide=self.hide_dropna),
                    make_hideable(
                        dbc.Col([ 
                            dbc.Label("pdp sample size"),
                            dbc.Input(id='pdp-sample-'+self.name, value=self.sample,
                                type="number", min=0, max=len(self.explainer), step=1),
                        ]), hide=self.hide_sample),  
                    make_hideable(   
                        dbc.Col([ #gridlines
                            dbc.Label("gridlines"),
                            dbc.Input(id='pdp-gridlines-'+self.name, value=self.gridlines,
                                    type="number", min=0, max=len(self.explainer), step=1),
                        ]), hide=self.hide_gridlines),
                    make_hideable(
                        dbc.Col([ #gridpoints
                            dbc.Label("gridpoints"),
                            dbc.Input(id='pdp-gridpoints-'+self.name, value=self.gridpoints,
                                type="number", min=0, max=100, step=1),
                        ]), hide=self.hide_gridpoints),
                ], form=True)
        ])
                
    def _register_callbacks(self, app):
        @app.callback(
            Output('pdp-graph-'+self.name, 'figure'),
            [Input('pdp-index-'+self.name, 'value'),
             Input('pdp-col-'+self.name, 'value'),
             Input('pdp-dropna-'+self.name, 'checked'),
             Input('pdp-sample-'+self.name, 'value'),
             Input('pdp-gridlines-'+self.name, 'value'),
             Input('pdp-gridpoints-'+self.name, 'value'),
             Input('pos-label', 'value')]
        )
        def update_pdp_graph(index, col, drop_na, sample, gridlines, gridpoints, pos_label):
            return self.explainer.plot_pdp(col, index, 
                drop_na=drop_na, sample=sample, gridlines=gridlines, gridpoints=gridpoints, 
                pos_label=pos_label)

        @app.callback(
            Output('pdp-col-'+self.name, 'options'),
            [Input('pdp-group-cats-'+self.name, 'checked')]
        )
        def update_pdp_graph(cats):
            col_options = [{'label': col, 'value':col} 
                                for col in self.explainer.columns_ranked_by_shap(cats)]
            return col_options
                        
