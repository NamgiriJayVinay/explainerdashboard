__all__ = [
    'PrecisionComponent',
    'ConfusionMatrixComponent',
    'LiftCurveComponent',
    'ClassificationComponent',
    'RocAucComponent',
    'PrAucComponent',
]

import dash
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_html_components as html

from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from .dashboard_methods import *


class PrecisionComponent(ExplainerComponent):
    def __init__(self, explainer, title="Precision Plot",
                    header_mode="none", name=None,
                    hide_cutoff=False, hide_binsize=False, hide_binmethod=False,
                    hide_multiclass=False,
                    bin_size=0.1, quantiles=10, cutoff=0.5,
                    quantiles_or_binsize='bin_size', multiclass=False):
        """Shows a precision graph with toggles.

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Precision Plot".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): Hide cutoff slider. Defaults to False.
            hide_binsize (bool, optional): hide binsize/quantiles slider. Defaults to False.
            hide_binmethod (bool, optional): Hide binsize/quantiles toggle. Defaults to False.
            hide_multiclass (bool, optional): Hide multiclass toggle. Defaults to False.
            bin_size (float, optional): Size of bins in probability space. Defaults to 0.1.
            quantiles (int, optional): Number of quantiles to divide plot. Defaults to 10.
            cutoff (float, optional): Cutoff to display in graph. Defaults to 0.5.
            quantiles_or_binsize (str, {'quantiles', 'bin_size'}, optional): Default bin method. Defaults to 'bin_size'.
            multiclass (bool, optional): Display all classes. Defaults to False.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff, self.hide_binsize = hide_cutoff, hide_binsize
        self.hide_binmethod, self.hide_multiclass = hide_binmethod, hide_multiclass
        
        self.bin_size, self.quantiles, self.cutoff = bin_size, quantiles, cutoff 
        self.quantiles_or_binsize, self.multiclass = quantiles_or_binsize, multiclass
        self.cutoff_name = 'precision-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dcc.Loading(id="loading-precision-graph-"+self.name, 
                                children=[dcc.Graph(id='precision-graph-'+self.name)]),
                    ], style={'margin': 0}),
                ])
            ]),
            dbc.Row([
                dbc.Col([
                    make_hideable(
                        html.Div([
                            dbc.Label('Bin size:', html_for='precision-binsize-'+self.name),
                            html.Div([
                                dcc.Slider(id='precision-binsize-'+self.name, 
                                        min = 0.01, max = 0.5, step=0.01, value=self.bin_size,
                                        marks={0.01: '0.01', 0.05: '0.05', 0.10: '0.10',
                                            0.20: '0.20', 0.25: '0.25' , 0.33: '0.33', 
                                            0.5: '0.5'}, 
                                        included=False,
                                        tooltip = {'always_visible' : False})
                            ], style={'margin-bottom': 5}),
                        ], id='precision-bin-size-div-'+self.name, style=dict(margin=5)),  
                    hide=self.hide_binsize),
                    make_hideable(
                        html.Div([
                            dbc.Label('Quantiles:', html_for='precision-quantiles-'+self.name),
                            html.Div([
                                dcc.Slider(id='precision-quantiles-'+self.name, 
                                            min = 1, max = 20, step=1, value=self.quantiles,
                                            marks={1: '1', 5: '5', 10: '10', 15: '15', 20:'20'}, 
                                            included=False,
                                            tooltip = {'always_visible' : False}),
                            ], style={'margin-bottom':5}),
                        ], id='precision-quantiles-div-'+self.name), hide=self.hide_binsize),
                    make_hideable(
                        html.Div([
                            html.Label('Cutoff prediction probability:'),
                            dcc.Slider(id='precision-cutoff-'+self.name, 
                                        min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                        marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                                0.75: '0.75', 0.99: '0.99'}, 
                                        included=False,
                                        tooltip = {'always_visible' : False})
                        ], style={'margin-bottom': 5}), hide=self.hide_cutoff),
                ]),
            ]),
            dbc.Row([
                make_hideable(
                    dbc.Col([
                        dbc.Label('Binning Method:', html_for='precision-binsize-or-quantiles-'+self.name),
                        dbc.RadioItems(
                            id='precision-binsize-or-quantiles-'+self.name,
                            options=[
                                {'label': 'Bin Size', 
                                'value': 'bin_size'},
                                {'label': 'Quantiles', 
                                'value': 'quantiles'}
                            ],
                            value=self.quantiles_or_binsize,
                            inline=True),
                    ], width=3), hide=self.hide_binmethod),
                make_hideable(
                    dbc.Col([
                        dbc.FormGroup([
                                dbc.RadioButton(
                                    id="precision-multiclass-"+self.name, 
                                    className="form-check-input",
                                    checked=self.multiclass
                                ),
                                dbc.Label(
                                    "Display all classes",
                                    html_for="precision-multiclass-"+self.name,
                                    className="form-check-label",
                                ),
                                
                        ], check=True),
                    ], width=3), hide=self.hide_multiclass), 
            ])    
        ])

    def _register_callbacks(self, app):
        @app.callback(
            [Output('precision-bin-size-div-'+self.name, 'style'),
             Output('precision-quantiles-div-'+self.name, 'style')],
            [Input('precision-binsize-or-quantiles-'+self.name, 'value')],
        )
        def update_div_visibility(bins_or_quantiles):
            if self.hide_binsize:
                return dict(display='none'), dict(display='none')
            if bins_or_quantiles=='bin_size':
                return {}, dict(display='none')
            elif bins_or_quantiles=='quantiles':
                return dict(display='none'), {}
            raise PreventUpdate   

        @app.callback(
            Output('precision-graph-'+self.name, 'figure'),
            [Input('precision-binsize-'+self.name, 'value'),
             Input('precision-quantiles-'+self.name, 'value'),
             Input('precision-binsize-or-quantiles-'+self.name, 'value'),
             Input('precision-cutoff-'+self.name, 'value'),
             Input('precision-multiclass-'+self.name, 'checked'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')],
        )
        def update_precision_graph(bin_size, quantiles, bins, cutoff, multiclass, pos_label, tab):
            if bins == 'bin_size':
                return self.explainer.plot_precision(
                    bin_size=bin_size, cutoff=cutoff, multiclass=multiclass, pos_label=pos_label)
            elif bins == 'quantiles':
                return self.explainer.plot_precision(
                    quantiles=quantiles, cutoff=cutoff, multiclass=multiclass, pos_label=pos_label)
            raise PreventUpdate


class ConfusionMatrixComponent(ExplainerComponent):
    def __init__(self, explainer, title="Confusion Matrix",
                    header_mode="none", name=None,
                    hide_cutoff=False, hide_percentage=False, hide_binary=False,
                    cutoff=0.5, percentage=True, binary=True):
        """Display confusion matrix component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Confusion Matrix".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): Hide cutoff slider. Defaults to False.
            hide_percentage (bool, optional): Hide percentage toggle. Defaults to False.
            hide_binary (bool, optional): Hide binary toggle. Defaults to False.
            cutoff (float, optional): Default cutoff. Defaults to 0.5.
            percentage (bool, optional): Display percentages instead of counts. Defaults to True.
            binary (bool, optional): Show binary instead of multiclass confusion matrix. Defaults to True.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff, self.hide_percentage = hide_cutoff, hide_percentage
        self.hide_binary = hide_binary
        self.cutoff, self.percentage, self.binary = cutoff, percentage, binary
        self.cutoff_name = 'confusionmatrix-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            dcc.Loading(id='loading-confusionmatrix-graph-'+self.name, 
                            children=[dcc.Graph(id='confusionmatrix-graph-'+self.name)]),
            make_hideable(
                html.Div([
                    html.Label('Cutoff prediction probability:'),
                    dcc.Slider(id='confusionmatrix-cutoff-'+self.name, 
                                min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                        0.75: '0.75', 0.99: '0.99'}, 
                                included=False,
                                tooltip = {'always_visible' : False})
                ], style={'margin-bottom': 25}), hide=self.hide_cutoff),
            make_hideable(
                html.Div([
                    dbc.FormGroup([
                            dbc.RadioButton(
                                id='confusionmatrix-percentage-'+self.name, 
                                className="form-check-input", 
                                checked=self.percentage
                            ),
                            dbc.Label(
                                "Display percentages",
                                html_for="confusionmatrix-percentage-"+self.name,
                                className="form-check-label",
                            ),
                    ], check=True),
                ]), hide=self.hide_percentage),
            make_hideable(
                html.Div([
                    dbc.FormGroup([
                            dbc.RadioButton(
                                id="confusionmatrix-binary-"+self.name, 
                                className="form-check-input", 
                                checked=self.binary
                            ),
                            dbc.Label(
                                "Binary (use cutoff for positive vs not positive)",
                                html_for="confusionmatrix-binary-"+self.name,
                                className="form-check-label",
                            ),
                    ], check=True),
                ]), hide=self.hide_binary),
        ])

    def _register_callbacks(self, app):
        @app.callback(
             Output('confusionmatrix-graph-'+self.name, 'figure'),
            [Input('confusionmatrix-cutoff-'+self.name, 'value'),
             Input('confusionmatrix-percentage-'+self.name, 'checked'),
             Input('confusionmatrix-binary-'+self.name, 'checked'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')],
        )
        def update_confusionmatrix_graph(cutoff, normalized, binary, pos_label, tab):
            return self.explainer.plot_confusion_matrix(
                        cutoff=cutoff, normalized=normalized, binary=binary, pos_label=pos_label)


class LiftCurveComponent(ExplainerComponent):
    def __init__(self, explainer, title="Lift Curve",
                    header_mode="none", name=None,
                    hide_cutoff=False, hide_percentage=False,
                    cutoff=0.5, percentage=True):
        """Show liftcurve component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Lift Curve".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): Hide cutoff slider. Defaults to False.
            hide_percentage (bool, optional): Hide percentage toggle. Defaults to False.
            cutoff (float, optional): Cutoff for lift curve. Defaults to 0.5.
            percentage (bool, optional): Display percentages instead of counts. Defaults to True.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff, self.hide_percentage = hide_cutoff, hide_percentage
        self.cutoff, self.percentage = cutoff, percentage
        self.cutoff_name = 'liftcurve-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            html.Div([
                        dcc.Loading(id='loading-lift-curve-'+self.name, 
                                children=[dcc.Graph(id='liftcurve-graph-'+self.name)]),
                    ], style={'margin': 0}),
            make_hideable(
                html.Div([
                    html.Label('Cutoff prediction probability:'),
                    dcc.Slider(id='liftcurve-cutoff-'+self.name, 
                                min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                        0.75: '0.75', 0.99: '0.99'}, 
                                included=False,
                                tooltip = {'always_visible' : False})
                ], style={'margin-bottom': 25}), hide=self.hide_cutoff),
            make_hideable(
                html.Div([
                    dbc.FormGroup([
                        dbc.RadioButton(
                            id="liftcurve-percentage-"+self.name, 
                            className="form-check-input", 
                            checked=True
                        ),
                        dbc.Label(
                            "Display percentages",
                            html_for="liftcurve-percentage-"+self.name,
                            className="form-check-label",
                        ),
                    ], check=True), 
                ]), hide=self.hide_percentage),         
        ])

    def _register_callbacks(self, app):
        @app.callback(
            Output('liftcurve-graph-'+self.name, 'figure'),
            [Input('liftcurve-cutoff-'+self.name, 'value'),
             Input('liftcurve-percentage-'+self.name, 'checked'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')],
        )
        def update_precision_graph(cutoff, percentage, pos_label, tab):
            return self.explainer.plot_lift_curve(cutoff=cutoff, percentage=percentage, pos_label=pos_label)


class ClassificationComponent(ExplainerComponent):
    def __init__(self, explainer, title="Classification Plot",
                    header_mode="none", name=None,
                    hide_cutoff=False, hide_percentage=False,
                    cutoff=0.5, percentage=True):
        """Shows a barchart of the number of classes above the cutoff and below
        the cutoff.

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "Classification Plot".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): Hide cutoff slider. Defaults to False.
            hide_percentage (bool, optional): Hide percentage toggle. Defaults to False.
            cutoff (float, optional): Cutoff for prediction. Defaults to 0.5.
            percentage (bool, optional): Show percentage instead of counts. Defaults to True.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff, self.hide_percentage = hide_cutoff, hide_percentage
        self.cutoff, percentage = cutoff, percentage
        self.cutoff_name = 'classification-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            html.Div([
                dcc.Loading(id="loading-classification-graph-"+self.name, 
                            children=[dcc.Graph(id='classification-graph-'+self.name)]),
            ], style={'margin': 0}),
            make_hideable(
                html.Div([
                    html.Label('Cutoff prediction probability:'),
                    dcc.Slider(id='classification-cutoff-'+self.name, 
                                min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                        0.75: '0.75', 0.99: '0.99'}, 
                                included=False,
                                tooltip = {'always_visible' : False})
                ], style={'margin-bottom': 25}), hide=self.hide_cutoff),
            make_hideable(
                html.Div([
                    dbc.FormGroup([
                        dbc.RadioButton(
                            id="classification-percentage-"+self.name, 
                            className="form-check-input", 
                            checked=True
                        ),
                        dbc.Label(
                            "Display percentages",
                            html_for="classification-percentage-"+self.name,
                            className="form-check-label",
                        ),
                    ], check=True),
                ]), hide=self.hide_percentage),
        ])

    def _register_callbacks(self, app):
        @app.callback(
            Output('classification-graph-'+self.name, 'figure'),
            [Input('classification-cutoff-'+self.name, 'value'),
             Input('classification-percentage-'+self.name, 'checked'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')],
        )
        def update_precision_graph(cutoff, percentage, pos_label, tab):
            return self.explainer.plot_classification(
                    cutoff=cutoff, percentage=percentage, pos_label=pos_label)


class RocAucComponent(ExplainerComponent):
    def __init__(self, explainer, title="ROC AUC Plot",
                    header_mode="none", name=None, 
                    hide_cutoff=False,
                    cutoff=0.5):
        """Show ROC AUC curve component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "ROC AUC Plot".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): Hide cutoff slider. Defaults to False.
            cutoff (float, optional): default cutoff. Defaults to 0.5.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff = hide_cutoff
        self.cutoff=cutoff
        self.cutoff_name = 'rocauc-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            dcc.Loading(id="loading-roc-auc-graph-"+self.name, 
                                children=[dcc.Graph(id='rocauc-graph-'+self.name)]),
            make_hideable(
                html.Div([
                    html.Label('Cutoff prediction probability:'),
                    dcc.Slider(id='rocauc-cutoff-'+self.name, 
                                min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                        0.75: '0.75', 0.99: '0.99'}, 
                                included=False,
                                tooltip = {'always_visible' : False},
                                updatemode='drag' )
                ], style={'margin-bottom': 25}), hide=self.hide_cutoff),
        ])

    def _register_callbacks(self, app):
        @app.callback(
            Output('rocauc-graph-'+self.name, 'figure'),
            [Input('rocauc-cutoff-'+self.name, 'value'),
             Input('pos-label', 'value'),
             Input('tabs', 'value')],
        )
        def update_precision_graph(cutoff, pos_label, tab):
            return self.explainer.plot_roc_auc(cutoff=cutoff, pos_label=pos_label)


class PrAucComponent(ExplainerComponent):
    def __init__(self, explainer, title="PR AUC Plot",
                    header_mode="none", name=None,
                    hide_cutoff=False,
                    cutoff=0.5):
        """Display PR AUC plot component

        Args:
            explainer (Explainer): explainer object constructed with either
                        ClassifierExplainer() or RegressionExplainer()
            title (str, optional): Title of tab or page. Defaults to 
                        "PR AUC Plot".
            header_mode (str, optional): {"standalone", "hidden" or "none"}. 
                        Defaults to "none".
            name (str, optional): unique name to add to Component elements. 
                        If None then random uuid is generated to make sure 
                        it's unique. Defaults to None.
            hide_cutoff (bool, optional): hide cutoff slider. Defaults to False.
            cutoff (float, optional): default cutoff. Defaults to 0.5.
        """
        super().__init__(explainer, title, header_mode, name)

        self.hide_cutoff = hide_cutoff
        self.cutoff = cutoff
        self.cutoff_name = 'prauc-cutoff-' + self.name
        self.register_dependencies("preds", "pred_probas", "pred_percentiles")

    def _layout(self):
        return html.Div([
            dcc.Loading(id="loading-pr-auc-graph-"+self.name, 
                                children=[dcc.Graph(id='prauc-graph-'+self.name)]),
            make_hideable(
                html.Div([
                    html.Label('Cutoff prediction probability:'),
                    dcc.Slider(id='prauc-cutoff-'+self.name, 
                                min = 0.01, max = 0.99, step=0.01, value=self.cutoff,
                                marks={0.01: '0.01', 0.25: '0.25', 0.50: '0.50',
                                        0.75: '0.75', 0.99: '0.99'}, 
                                included=False,
                                tooltip = {'always_visible' : False})
                ], style={'margin-bottom': 25}), hide=self.hide_cutoff),
        ])

    def _register_callbacks(self, app):
        @app.callback(
            Output('prauc-graph-'+self.name, 'figure'),
            [Input('prauc-cutoff-'+self.name, 'value'),
             Input('pos-label', 'value')],
            [State('tabs', 'value')],
        )
        def update_precision_graph(cutoff, pos_label, tab):
            return self.explainer.plot_pr_auc(cutoff=cutoff, pos_label=pos_label)