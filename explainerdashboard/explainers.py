__all__ = ['BaseExplainer', 
            'ClassifierExplainer', 
            'RegressionExplainer', 
            'RandomForestClassifierExplainer', 
            'RandomForestRegressionExplainer',
            'ClassifierBunch', # deprecated
            'RegressionBunch', # deprecated
            'RandomForestClassifierBunch', # deprecated
            'RandomForestRegressionBunch', # deprecated
            ]

from abc import ABC, abstractmethod
import warnings
import base64

import numpy as np
import pandas as pd

from pdpbox import pdp
import shap
from dtreeviz.trees import *

from sklearn.metrics import roc_auc_score, accuracy_score, f1_score
from sklearn.metrics import precision_score, recall_score, log_loss
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from .explainer_methods import *
from .explainer_plots import *
from .make_callables import make_callable, default_list, default_2darray


class BaseExplainer(ABC):
    """ """
    def __init__(self, model, X, y=None, permutation_metric=r2_score, 
                    shap="guess", X_background=None, model_output="raw",
                    cats=None, idxs=None, descriptions=None, 
                    permutation_cv=None, na_fill=-999):
        """Defines the basic functionality of an ExplainerBunch

        :param model: a model with a scikit-learn compatible .fit and .predict method
        :type model: [type]
        :param X: a pd.DataFrame with your model features
        :type X: pd.DataFrame
        :param y: Dependent variable of your model, defaults to None
        :type y: pd.Series, optional
        :param permutation_metric: is a scikit-learn compatible metric function (or string), 
            defaults to r2_score
        :type permutation_metric: metric function, optional
        :param shap: type of shap_explainer to fit: 'tree', 'linear', 'kernel', defaults to 'guess'
        :type shap: str
        :param X_background: background X to be used by shap explainer
        :type X_background: pd.DataFrame
        :param model_output: model_output of shap values, either 'raw', 'logodds' or 'probability'
        :type model_output: str
        :param cats: list of variables that have been onehotencoded. Allows to 
            group categorical variables together in plots, defaults to None
        :type cats: list, optional
        :param idxs: list of row identifiers. Can be names, id's, etc. Get 
            converted to str, defaults to None
        :type idxs: list, optional
        :param permutation_cv: If given permutation importances get calculated 
            using cross validation, defaults to None
        :type permutation_cv: int, optional
        :param na_fill: The filler used for missing values, defaults to -999
        :type na_fill: int, optional
        """
        self.model  = model
        self.X = X.reset_index(drop=True)
        self.X_background = X_background
        if y is not None:
            self.y = pd.Series(y).reset_index(drop=True)
        else:
            self.y = pd.Series(np.full(len(X), np.nan))
        
        self.metric = permutation_metric

        if shap == "guess":
            shap_guess = guess_shap(model)
            if shap_guess is not None:
                model_str = str(type(self.model))\
                    .replace("'", "").replace("<", "").replace(">", "")\
                    .split(".")[-1]
                print(f"Note: shap=='guess' so guessing for {model_str}"
                      f" shap='{shap_guess}'...")
                self.shap = shap_guess
            else:
                raise ValueError(
                    "Failed to guess the type of shap explainer to use. "
                    "Please explicitly pass either shap='tree', 'linear', "
                    "deep' or 'kernel'.")
        else:
            assert shap in ['tree', 'linear', 'deep', 'kernel'], \
                "Only shap='guess', 'tree', 'linear', 'deep', or ' kernel' allowed."
            self.shap = shap

        self.model_output = model_output

        self.cats = cats if cats is not None else []
        if idxs is not None:
            if isinstance(idxs, list):
                self.idxs = [str(i) for i in idxs]
            else:
                self.idxs = list(idxs.astype(str))
        elif idxs=="use_index":
            self.idxs = list(X.index.astype(str))
        else:
            self.idxs = [str(i) for i in range(len(X))]
        self.descriptions = {} if descriptions is None else descriptions
        self.permutation_cv = permutation_cv
        self.na_fill = na_fill
        self.columns = self.X.columns.tolist()
        self.is_classifier = False
        self.is_regression = False
        self.interactions_should_work = True
        _ = self.shap_explainer

    def __len__(self):
        return len(self.X)

    def __contains__(self, index):
        if self.get_int_idx(index) is not None:
            return True
        return False

    def check_cats(self, col1, col2=None):
        """check whether should use cats=True based on col1 (and col2)

        Args:
          col1: First column
          col2:  Second column (Default value = None)

        Returns:
          Boolean whether cats should be True

        """
        if col2 is None:
            if col1 in self.columns:
                return False
            elif col1 in self.columns_cats:
                return True
            raise ValueError(f"Can't find {col1}.")
        
        if col1 not in self.columns and col1 not in self.columns_cats:
            raise ValueError(f"Can't find {col1}.")
        if col2 not in self.columns and col2 not in self.columns_cats:
            raise ValueError(f"Can't find {col2}.")
        
        if col1 in self.columns and col2 in self.columns:
            return False
        if col1 in self.columns_cats and col2 in self.columns_cats:
            return True
        if col1 in self.columns_cats and not col2 in self.columns_cats:
            raise ValueError(
                f"{col1} is categorical but {col2} is not in columns_cats")
        if col2 in self.columns_cats and not col1 in self.columns_cats:
            raise ValueError(
                f"{col2} is categorical but {col1} is not in columns_cats")

    @property
    def shap_explainer(self):
        """ """
        if not hasattr(self, '_shap_explainer'):
            X_str = ", X_background" if self.X_background is not None else 'X'
            NoX_str = ", X_background" if self.X_background is not None else ''
            if self.shap == 'tree':
                print("Generating self.shap_explainer = "
                      f"shap.TreeExplainer(model{NoX_str})")
                self._shap_explainer = shap.TreeExplainer(self.model, self.X_background)
            elif self.shap=='linear':
                if self.X_background is None:
                    print(
                        "Warning: shap values for shap.LinearExplainer get "
                        "calculated against X_background, but paramater "
                        "X_background=None, so using X instead")
                print(f"Generating self.shap_explainer = shap.LinearExplainer(model, {X_str})...")
                self._shap_explainer = shap.LinearExplainer(self.model, 
                    self.X_background if self.X_background is not None else self.X)
            elif self.shap=='deep':
                print(f"Generating self.shap_explainer = "
                      f"shap.DeepExplainer(model{NoX_str})")
                self._shap_explainer = shap.DeepExplainer(self.model)
            elif self.shap=='kernel': 
                if self.X_background is None:
                    print(
                        "Warning: shap values for shap.LinearExplainer get "
                        "calculated against X_background, but paramater "
                        "X_background=None, so using X instead")
                print("Generating self.shap_explainer = "
                        f"shap.KernelExplainer(model, {X_str})...")
                self._shap_explainer = shap.KernelExplainer(self.model, 
                    self.X_background if self.X_background is not None else self.X)
        return self._shap_explainer

    def get_int_idx(self, index):
        """Turn str index into an int index

        Args:
          index(str or int): 

        Returns:
            int index
        """
        if isinstance(index, int):
            if index >= 0 and index < len(self):
                return index
        elif isinstance(index, str):
            if self.idxs is not None and index in self.idxs:
                return self.idxs.index(index)
        return None

    def random_index(self, y_min=None, y_max=None, pred_min=None, pred_max=None, 
                        return_str=False, **kwargs):
        """random index following constraints

        Args:
          y_min:  (Default value = None)
          y_max:  (Default value = None)
          pred_min:  (Default value = None)
          pred_max:  (Default value = None)
          return_str:  (Default value = False)
          **kwargs: 

        Returns:
          if y_values is given select an index for which y in y_values
          if return_str return str index from self.idxs

        """
        if y_min is None:
            y_min = self.y.min()
        if y_max is None:
            y_max = self.y.max()
        if pred_min is None:
            pred_min = self.preds.min()
        if pred_max is None:
            pred_max = self.preds.max()

        potential_idxs = self.y[(self.y>=y_min) & 
                                (self.y <= y_max) & 
                                (self.preds>=pred_min) & 
                                (self.preds <= pred_max)].index

        if len(potential_idxs) > 0:
            idx = np.random.choice(potential_idxs)
        else:
            return None
        if return_str:
            assert self.idxs is not None, \
                "no self.idxs property found..."
            return self.idxs[idx]
        return int(idx)

    @property
    def preds(self):
        """returns model model predictions"""
        if not hasattr(self, '_preds'):
            print("Calculating predictions...")
            self._preds = self.model.predict(self.X)
            
        return self._preds
    
    @property
    def pred_percentiles(self):
        """returns percentile rank of model predictions"""
        if not hasattr(self, '_pred_percentiles'):
            print("Calculating prediction percentiles...")
            self._pred_percentiles = (pd.Series(self.preds)
                                .rank(method='min')
                                .divide(len(self.preds))
                                .values)
        return make_callable(self._pred_percentiles)

    def columns_ranked_by_shap(self, cats=False, pos_label=None):
        """returns the columns of X, ranked by mean abs shap value

        Args:
          cats: Group categorical together (Default value = False)
          pos_label:  (Default value = None)

        Returns:
          list of columns

        """
        if cats:
            return self.mean_abs_shap_cats(pos_label).Feature.tolist()
        else:
            return self.mean_abs_shap(pos_label).Feature.tolist()

    def n_features(self, cats=False):
        """number of features with cats=True or cats=False

        Args:
          cats:  (Default value = False)

        Returns:
            int, number of features

        """
        if cats:
            return len(self.columns_cats)
        else:
            return len(self.columns)

    def equivalent_col(self, col):
        """Find equivalent col in columns_cats or columns
        
        if col in self.columns, return equivalent col in self.columns_cats,
                e.g. equivalent_col('Gender_Male') -> 'Gender'
        if col in self.columns_cats, return first one hot encoded col,
                e.g. equivalent_col('Gender') -> 'Gender_Male'
        
        (useful for switching between cats=True and cats=False, while
            maintaining column selection)

        Args:
          col:  col to get equivalent col for

        Returns:
          col

        """
        if col in self.columns_cats:
            # first onehot-encoded columns
            return get_feature_dict(self.columns, self.cats)[col][0]
        elif col in self.columns:
            # the cat that the col belongs to
            return [k for k, v 
                        in get_feature_dict(self.columns, self.cats).items() 
                            if col in v][0]
        return None

    def description(self, col):
        """returns the written out description of what feature col means

        Args:
          col(str): col to get description for

        Returns:
            str, description
        """
        if col in self.descriptions.keys():
            return self.descriptions[col]
        elif self.equivalent_col(col) in  self.descriptions.keys():
            return self.descriptions[self.equivalent_col(col)]
        return ""

    def description_list(self, cols):
        """returns a list of descriptions of a list of cols

        Args:
          cols(list): cols to be converted to descriptions

        Returns:
            list of descriptions
        """
        return [self.description(col) for col in cols]

    def get_col(self, col):
        """return pd.Series with values of col

        For categorical feature reverse engineers the onehotencoding.

        Args:
          col: column tof values to be returned

        Returns:
          pd.Series with values of col

        """
        assert col in self.columns or col in self.cats, \
            f"{col} not in columns!"

        if col in self.X.columns:
            return self.X[col]
        elif col in self.cats:
            return retrieve_onehot_value(self.X, col)
        
    def get_col_value_plus_prediction(self, index, col):
        """return value of col and prediction for index

        Args:
          index: index row
          col: feature col

        Returns:
          tupe(value of col, prediction for index)

        """
        assert index in self, f"index {index} not found"
        assert (col in self.X.columns) or (col in self.cats),\
            f"{col} not in columns of dataset"

        idx = self.get_int_idx(index)

        if col in self.X.columns:
            col_value = self.X[col].iloc[idx]
        elif col in self.cats:
            col_value = retrieve_onehot_value(self.X, col).iloc[idx]

        try:
            prediction = self.pred_probas[idx]
        except:
            prediction = self.preds[idx]

        return col_value, prediction

    @property
    def permutation_importances(self):
        """Permutation importances """
        if not hasattr(self, '_perm_imps'):
            print("Calculating importances...")
            self._perm_imps = cv_permutation_importances(
                            self.model, self.X, self.y, self.metric,
                            cv=self.permutation_cv,
                            needs_proba=self.is_classifier)
        return make_callable(self._perm_imps)

    @property
    def permutation_importances_cats(self):
        """permutation importances with categoricals grouped"""
        if not hasattr(self, '_perm_imps_cats'):
            self._perm_imps_cats = cv_permutation_importances(
                            self.model, self.X, self.y, self.metric, self.cats,
                            cv=self.permutation_cv,
                            needs_proba=self.is_classifier)
        return make_callable(self._perm_imps_cats)

    @property
    def X_cats(self):
        """X with categorical variables grouped together"""
        if not hasattr(self, '_X_cats'):
            self._X_cats = merge_categorical_columns(self.X, self.cats)
        return self._X_cats

    @property
    def columns_cats(self):
        """columns of X with categorical features grouped"""
        if not hasattr(self, '_columns_cats'):
            self._columns_cats = self.X_cats.columns.tolist()
        return self._columns_cats

    @property
    def shap_base_value(self):
        """the intercept for the shap values.
        
        (i.e. 'what would the prediction be if we knew none of the features?')
        """
        if not hasattr(self, '_shap_base_value'):
            # CatBoost needs shap values calculated before expected value
            _ = self.shap_values() 
            self._shap_base_value = self.shap_explainer.expected_value
            if isinstance(self._shap_base_value, np.ndarray):
                # shap library now returns an array instead of float
                self._shap_base_value = self._shap_base_value.item()
        return make_callable(self._shap_base_value)

    @property
    def shap_values(self):
        """SHAP values calculated using the shap library"""
        if not hasattr(self, '_shap_values'):
            print("Calculating shap values...")
            self._shap_values = self.shap_explainer.shap_values(self.X)
        return make_callable(self._shap_values)
    
    @property
    def shap_values_cats(self):
        """SHAP values when categorical features have been grouped"""
        if not hasattr(self, '_shap_values_cats'):
            print("Calculating shap values...")
            self._shap_values_cats = merge_categorical_shap_values(
                    self.X, self.shap_values, self.cats)
        return make_callable(self._shap_values_cats)

    @property
    def shap_interaction_values(self):
        """SHAP interaction values calculated using shap library"""
        assert self.shap != 'linear', \
            "Unfortunately shap.LinearExplainer does not provide " \
            "shap interaction values! So no interactions tab!"
        if not hasattr(self, '_shap_interaction_values'):
            print("Calculating shap interaction values...")
            self._shap_interaction_values = \
                self.shap_explainer.shap_interaction_values(self.X)
        return make_callable(self._shap_interaction_values)

    @property
    def shap_interaction_values_cats(self):
        """SHAP interaction values with categorical features grouped"""
        if not hasattr(self, '_shap_interaction_values_cats'):
            print("Calculating shap interaction values...")
            self._shap_interaction_values_cats = \
                merge_categorical_shap_interaction_values(
                    self.X, self.X_cats, self.shap_interaction_values)
        return make_callable(self._shap_interaction_values_cats)

    @property
    def mean_abs_shap(self):
        """Mean absolute SHAP values per feature."""
        if not hasattr(self, '_mean_abs_shap'):
            self._mean_abs_shap = mean_absolute_shap_values(
                                self.columns, self.shap_values)
        return make_callable(self._mean_abs_shap)

    @property
    def mean_abs_shap_cats(self):
        """Mean absolute SHAP values with categoricals grouped."""
        if not hasattr(self, '_mean_abs_shap_cats'):
            self._mean_abs_shap_cats = mean_absolute_shap_values(
                                self.columns, self.shap_values, self.cats)
        return make_callable(self._mean_abs_shap_cats)

    def calculate_properties(self, include_interactions=True):
        """Explicitely calculates all lazily calculated properties.
        Useful so that properties are not calculate multiple times in 
        parallel when starting a dashboard.

        Args:
          include_interactions(bool, optional, optional): shap interaction values can take a long
        time to compute for larger datasets with more features. Therefore you
        can choose not to calculate these, defaults to True

        Returns:

        """
        _ = (self.preds, self.permutation_importances,
                self.shap_base_value, self.shap_values,
                self.mean_abs_shap)
        if self.cats is not None:
            _ = (self.mean_abs_shap_cats, self.X_cats,
                    self.shap_values_cats)
        if include_interactions:
            _ = self.shap_interaction_values
            if self.cats is not None:
                _ = self.shap_interaction_values_cats

    def metrics(self, *args, **kwargs):
        """returns a dict of metrics.
        
        Implemented by either ClassifierExplainer or RegressionExplainer
        """
        return {}

    def metrics_markdown(self, round=2, **kwargs):
        """markdown makeup of self.metrics() dict

        Args:
          round:  (Default value = 2)
          **kwargs: 

        Returns:

        """
        metrics_dict = self.metrics(**kwargs)
        
        metrics_markdown = "# Model Summary: \n\n"
        for k, v in metrics_dict.items():
            metrics_markdown += f"### {k}: {np.round(v, round)}\n"
        return metrics_markdown
    
    def mean_abs_shap_df(self, topx=None, cutoff=None, cats=False, pos_label=None):
        """sorted dataframe with mean_abs_shap
        
        returns a pd.DataFrame with the mean absolute shap values per features,
        sorted rom highest to lowest.

        Args:
          topx(int, optional, optional): Only return topx most importance features, defaults to None
          cutoff(float, optional, optional): Only return features with mean abs shap of at least cutoff, defaults to None
          cats(bool, optional, optional): group categorical variables, defaults to False
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame: shap_df

        """
        shap_df = self.mean_abs_shap_cats(pos_label) if cats \
                        else self.mean_abs_shap(pos_label)

        if topx is None: topx = len(shap_df)
        if cutoff is None: cutoff = shap_df['MEAN_ABS_SHAP'].min()
        return (shap_df[shap_df['MEAN_ABS_SHAP'] >= cutoff]
                    .sort_values('MEAN_ABS_SHAP', ascending=False).head(topx))

    def shap_top_interactions(self, col, topx=None, cats=False, pos_label=None):
        """returns the features that interact with feature col in descending order.
        
        if shap interaction values have already been calculated, use those.
        Otherwise use shap approximate_interactions or simply mean abs shap.

        Args:
          col(str): feature for which you want to get the interactions
          topx(int, optional, optional): Only return topx features, defaults to None
          cats(bool, optional, optional): Group categorical features, defaults to False
          pos_label:  (Default value = None)

        Returns:
          list: top_interactions

        """
        if cats:
            if hasattr(self, '_shap_interaction_values'):
                col_idx = self.X_cats.columns.get_loc(col)
                top_interactions = self.X_cats.columns[
                    np.argsort(
                        -np.abs(self.shap_interaction_values_cats(
                            pos_label)[:, col_idx, :]).mean(0))].tolist()
            else:
                top_interactions = self.mean_abs_shap_cats(pos_label)\
                                        .Feature.values.tolist()
                top_interactions.insert(0, top_interactions.pop(
                    top_interactions.index(col))) #put col first

            if topx is None: topx = len(top_interactions)
            return top_interactions[:topx]
        else:
            if hasattr(self, '_shap_interaction_values'):
                col_idx = self.X.columns.get_loc(col)
                top_interactions = self.X.columns[np.argsort(-np.abs(
                            self.shap_interaction_values(
                                pos_label)[:, col_idx, :]).mean(0))].tolist()
            else:
                interaction_idxs = shap.common.approximate_interactions(
                    col, self.shap_values(pos_label), self.X)
                top_interactions = self.X.columns[interaction_idxs].tolist()
                #put col first
                top_interactions.insert(0, top_interactions.pop(-1)) 

            if topx is None: topx = len(top_interactions)
            return top_interactions[:topx]

    def shap_interaction_values_by_col(self, col, cats=False, pos_label=None):
        """returns the shap interaction values[np.array(N,N)] for feature col

        Args:
          col(str): features for which you'd like to get the interaction value
          cats(bool, optional, optional): group categorical, defaults to False
          pos_label:  (Default value = None)

        Returns:
          np.array(N,N): shap_interaction_values

        """
        if cats:
            return self.shap_interaction_values_cats(pos_label)[:,
                        self.X_cats.columns.get_loc(col), :]
        else:
            return self.shap_interaction_values(pos_label)[:,
                        self.X.columns.get_loc(col), :]

    def permutation_importances_df(self, topx=None, cutoff=None, cats=False, 
                                    pos_label=None):
        """dataframe with features ordered by permutation importance.
        
        For more about permutation importances.
        
        see https://explained.ai/rf-importance/index.html

        Args:
          topx(int, optional, optional): only return topx most important 
                features, defaults to None
          cutoff(float, optional, optional): only return features with importance 
                of at least cutoff, defaults to None
          cats(bool, optional, optional): Group categoricals, defaults to False
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame: importance_df

        """
        if cats:
            importance_df = (self.permutation_importances_cats(pos_label)
                                .reset_index()) 
        else:
            importance_df = (self.permutation_importances(pos_label)
                                .reset_index())

        if topx is None: topx = len(importance_df)
        if cutoff is None: cutoff = importance_df.Importance.min()
        return importance_df[importance_df.Importance > cutoff].head(topx)

    def importances_df(self, kind="shap", topx=None, cutoff=None, cats=False, 
                        pos_label=None):
        """wrapper function for mean_abs_shap_df() and permutation_importance_df()

        Args:
          kind(str): 'shap' or 'permutations'  (Default value = "shap")
          topx: only display topx highest features (Default value = None)
          cutoff: only display features above cutoff (Default value = None)
          cats: Group categoricals (Default value = False)
          pos_label: Positive class (Default value = None)

        Returns:
          pd.DataFrame

        """
        assert kind=='shap' or kind=='permutation', \
                "kind should either be 'shap' or 'permutation'!"
        if kind=='permutation':
            return self.permutation_importances_df(topx, cutoff, cats, pos_label)
        elif kind=='shap':
            return self.mean_abs_shap_df(topx, cutoff, cats, pos_label)

    def contrib_df(self, index, cats=True, topx=None, cutoff=None, 
                    pos_label=None):
        """shap value contributions to the prediction for index.
        
        Used as input for the plot_contributions() method.

        Args:
          index(int or str): index for which to calculate contributions
          cats(bool, optional, optional): Group categoricals, defaults to True
          topx(int, optional, optional): Only return topx features, remainder 
                    called REST, defaults to None
          cutoff(float, optional, optional): only return features with at least 
                    cutoff contributions, defaults to None
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame: contrib_df

        """
        idx = self.get_int_idx(index)
        if cats:
            return get_contrib_df(self.shap_base_value(pos_label), 
                                    self.shap_values_cats(pos_label)[idx],
                                    self.X_cats.iloc[[idx]], topx, cutoff)
        else:
            return get_contrib_df(self.shap_base_value(pos_label), 
                                    self.shap_values(pos_label)[idx],
                                    self.X.iloc[[idx]], topx, cutoff)

    def contrib_summary_df(self, index, cats=True,
                            topx=None, cutoff=None, round=2, pos_label=None):
        """Takes a contrib_df, and formats it to a more human readable format

        Args:
          index: index to show contrib_summary_df for
          cats: Group categoricals (Default value = True)
          topx: Only show topx highest features(Default value = None)
          cutoff: Only show features above cutoff (Default value = None)
          round: round figures (Default value = 2)
          pos_label: Positive class (Default value = None)

        Returns:
          pd.DataFrame
        """
        idx = self.get_int_idx(index) # if passed str convert to int index
        return get_contrib_summary_df(
                    self.contrib_df(idx, cats, topx, cutoff, pos_label), 
                    round=round)

    def interactions_df(self, col, cats=False, topx=None, cutoff=None, 
                            pos_label=None):
        """dataframe of mean absolute shap interaction values for col

        Args:
          col: Feature to get interactions_df for
          cats: Group categoricals (Default value = False)
          topx: Only display topx most important features (Default value = None)
          cutoff: Only display features with mean abs shap of at least cutoff (Default value = None)
          pos_label: Positive class  (Default value = None)

        Returns:
          pd.DataFrame

        """
        importance_df = mean_absolute_shap_values(
            self.columns_cats if cats else self.columns, 
            self.shap_interaction_values_by_col(col, cats, pos_label))

        if topx is None: topx = len(importance_df)
        if cutoff is None: cutoff = importance_df.MEAN_ABS_SHAP.min()
        return importance_df[importance_df.MEAN_ABS_SHAP > cutoff].head(topx)
    
    def formatted_contrib_df(self, index, round=None, lang='en', 
                                pos_label=None):
        """contrib_df formatted in a particular idiosyncratic way.
        
        Additional language option for output in Dutch (lang='nl')

        Args:
          index(str or int): index to return contrib_df for
          round(int, optional, optional): rounding of continuous features, defaults to 2
          lang(str, optional, optional): language to name the columns, defaults to 'en'
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame: formatted_contrib_df

        """
        cdf = self.contrib_df(index, cats=True, pos_label=pos_label).copy()
        cdf.reset_index(inplace=True)
        cdf.loc[cdf.col=='base_value', 'value'] = np.nan
        cdf['row_id'] = self.get_int_idx(index)
        cdf['name_id'] = self.idxs[self.get_int_idx(index)]
        cdf['cat_value'] = np.where(cdf.col.isin(self.cats), cdf.value, np.nan)
        cdf['cont_value'] = np.where(cdf.col.isin(self.cats), np.nan, cdf.value)
        if round is not None:
            rounded_cont = np.round(cdf['cont_value'].values.astype(float), round)
            cdf['value'] = np.where(cdf.col.isin(self.cats), cdf.cat_value, rounded_cont)
        cdf['type'] = np.where(cdf.col.isin(self.cats), 'cat', 'cont')
        cdf['abs_contribution'] = np.abs(cdf.contribution)
        cdf = cdf[['row_id', 'name_id', 'contribution', 'abs_contribution',
                    'col', 'value', 'cat_value', 'cont_value', 'type', 'index']]
        if lang == 'nl':
            cdf.columns = ['row_id', 'name_id', 'SHAP', 'ABS_SHAP', 'Variabele', 'Waarde',
                            'Cat_Waarde', 'Cont_Waarde', 'Waarde_Type', 'Variabele_Volgorde']
            return cdf

        cdf.columns = ['row_id', 'name_id', 'SHAP', 'ABS_SHAP', 'Feature', 'Value',
                        'Cat_Value', 'Cont_Value', 'Value_Type', 'Feature_Order']
        return cdf

    def get_pdp_result(self, col, index=None, drop_na=True,
                        sample=500, num_grid_points=20, pos_label=None):
        """Uses the PDPBox to calculate partial dependences for feature col.

        Args:
          col(str): Feature to calculate partial dependences for
          index(int or str, optional, optional): Index of row to put at iloc[0], defaults to None
          drop_na(bool, optional, optional): drop rows where col equals na_fill, defaults to True
          sample(int, optional, optional): Number of rows to sample for plot, defaults to 500
          num_grid_points(ints: int, optional, optional): Number of grid points to calculate, default 20
          pos_label:  (Default value = None)

        Returns:
          PDPBox.pdp_result: pdp_result

        """
        assert col in self.X.columns or col in self.cats, \
            f"{col} not in columns of dataset"
        if col in self.columns and not col in self.columns_cats:
            features = col
        else:
            features = get_feature_dict(self.X.columns, self.cats)[col]

        if index is not None:
            idx = self.get_int_idx(index)
            if len(features)==1 and drop_na: # regular col, not onehotencoded
                sample_size=min(sample, len(self.X[(self.X[features[0]] != self.na_fill)])-1)
                sampleX = pd.concat([
                    self.X[self.X.index==idx],
                    self.X[(self.X.index!=idx) & (self.X[features[0]] != self.na_fill)]\
                            .sample(sample_size)],
                    ignore_index=True, axis=0)
            else:
                sample_size = min(sample, len(self.X)-1)
                sampleX = pd.concat([
                    self.X[self.X.index==idx],
                    self.X[(self.X.index!=idx)].sample(sample_size)],
                    ignore_index=True, axis=0)
        else:
            if len(features)==1 and drop_na: # regular col, not onehotencoded
                sample_size=min(sample, len(self.X[(self.X[features[0]] != self.na_fill)])-1)
                sampleX = self.X[(self.X[features[0]] != self.na_fill)]\
                                .sample(sample_size)
            else:
                sampleX = self.X.sample(min(sample, len(self.X)))

        # if only a single value (i.e. not onehot encoded, take that value
        # instead of list):
        if len(features)==1: features=features[0]
        pdp_result = pdp.pdp_isolate(
                model=self.model, dataset=sampleX,
                model_features=self.X.columns,
                num_grid_points=num_grid_points, feature=features)
        if isinstance(features, list):
            # strip 'col_' from the grid points
            if isinstance(pdp_result, list):
                for i in range(len(pdp_result)):
                    pdp_result[i].feature_grids = \
                        pd.Series(pdp_result[i].feature_grids).str.split(col+'_').str[1].values
            else:
                pdp_result.feature_grids = \
                        pd.Series(pdp_result.feature_grids).str.split(col+'_').str[1].values
                
        return pdp_result

    def get_dfs(self, cats=True, round=None, lang='en', pos_label=None):
        """return three summary dataframes for storing main results
        
        Returns three pd.DataFrames. The first with id, prediction, actual and
        feature values, the second with only id and shap values. The third
        is similar to contrib_df for every id.
        These can then be used to build your own custom dashboard on these data,
        for example using PowerBI.

        Args:
          cats(bool, optional, optional): group categorical variables, defaults to True
          round(int, optional, optional): how to round shap values (Default value = None)
          lang(str, optional, optional): language to format dfs in. Defaults to 'en', 'nl' also available
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame, pd.DataFrame, pd.DataFrame: cols_df, shap_df, contribs_df

        """
        if cats:
            cols_df = self.X_cats.copy()
            shap_df = pd.DataFrame(self.shap_values_cats(pos_label), columns = self.X_cats.columns)
        else:
            cols_df = self.X.copy()
            shap_df = pd.DataFrame(self.shap_values(pos_label), columns = self.X.columns)

        actual_str = 'Uitkomst' if lang == 'nl' else 'Actual'
        prediction_str = 'Voorspelling' if lang == 'nl' else 'Prediction'
        
        cols_df.insert(0, actual_str, self.y )
        if self.is_classifier:
            cols_df.insert(0, prediction_str, self.pred_probas)
        else:
            cols_df.insert(0, prediction_str, self.preds)
        cols_df.insert(0, 'name_id', self.idxs)
        cols_df.insert(0, 'row_id', range(len(self)))
 
        shap_df.insert(0, 'SHAP_base', np.repeat(self.shap_base_value, len(self)))
        shap_df.insert(0, 'name_id', self.idxs)
        shap_df.insert(0, 'row_id', range(len(self)))


        contribs_df = None
        for idx in range(len(self)):
            fcdf = self.formatted_contrib_df(idx, round=round, lang=lang)
            if contribs_df is None: contribs_df = fcdf
            else: contribs_df = pd.concat([contribs_df, fcdf])

        return cols_df, shap_df, contribs_df

    def to_sql(self, conn, schema, name, if_exists='replace',
                cats=True, round=None, lang='en', pos_label=None):
        """Writes three dataframes generated by .get_dfs() to a sql server.
        
        Tables will be called name_COLS and name_SHAP and name_CONTRBIB

        Args:
          conn(sqlalchemy.engine.Engine or sqlite3.Connection):     
                    database connecter acceptable for pd.to_sql
          schema(str): schema to write to
          name(str): name prefix of tables
          cats(bool, optional, optional): group categorical variables, defaults to True
          if_exists({'fail’, ‘replace’, ‘append’}, default ‘replace’, optional): 
                    How to behave if the table already exists. (Default value = 'replace')
          round(int, optional, optional): how to round shap values (Default value = None)
          lang(str, optional, optional): language to format dfs in. Defaults to 'en', 'nl' also available
          pos_label:  (Default value = None)

        Returns:

        """
        cols_df, shap_df, contribs_df = self.get_dfs(cats, round, lang, pos_label)
        cols_df.to_sql(con=conn, schema=schema, name=name+"_COLS",
                        if_exists=if_exists, index=False)
        shap_df.to_sql(con=conn, schema=schema, name=name+"_SHAP",
                        if_exists=if_exists, index=False)
        contribs_df.to_sql(con=conn, schema=schema, name=name+"_CONTRIB",
                        if_exists=if_exists, index=False)

    def plot_importances(self, kind='shap', topx=None, cats=False, round=3, pos_label=None):
        """plot barchart of importances in descending order.

        Args:
          type(str, optional): shap' for mean absolute shap values, 'permutation' for
                    permutation importances, defaults to 'shap'
          topx(int, optional, optional): Only return topx features, defaults to None
          cats(bool, optional, optional): Group categoricals defaults to False
          kind:  (Default value = 'shap')
          round:  (Default value = 3)
          pos_label:  (Default value = None)

        Returns:
          plotly.fig: fig

        """
        importances_df = self.importances_df(kind=kind, topx=topx, cats=cats, pos_label=pos_label)
        if self.descriptions:
            descriptions = self.description_list(importances_df.Feature)
            return plotly_importances_plot(importances_df, descriptions, round=round)
        else:
            return plotly_importances_plot(importances_df, round=round)


    def plot_interactions(self, col, cats=False, topx=None, pos_label=None):
        """plot mean absolute shap interaction value for col.

        Args:
          col: column for which to generate shap interaction value
          cats(bool, optional, optional): Group categoricals defaults to False
          topx(int, optional, optional): Only return topx features, defaults to None
          pos_label:  (Default value = None)

        Returns:
          plotly.fig: fig

        """
        if col in self.cats:
            cats = True
        interactions_df = self.interactions_df(col, cats=cats, topx=topx, pos_label=pos_label)
        return plotly_importances_plot(interactions_df)

    def plot_shap_contributions(self, index, cats=True,
                                    topx=None, cutoff=None, round=2, pos_label=None):
        """plot waterfall plot of shap value contributions to the model prediction for index.

        Args:
          index(int or str): index for which to display prediction
          cats(bool, optional, optional): Group categoricals, defaults to True
          topx(int, optional, optional): Only display topx features, defaults to None
          cutoff(float, optional, optional): Only display features with at least cutoff contribution, defaults to None
          round(int, optional, optional): round contributions to round precision, defaults to 2
          pos_label:  (Default value = None)

        Returns:
          plotly.Fig: fig

        """
        contrib_df = self.contrib_df(self.get_int_idx(index), cats, topx, cutoff, pos_label)
        return plotly_contribution_plot(contrib_df, model_output=self.model_output, round=round)

    def plot_shap_summary(self, topx=None, cats=False, pos_label=None):
        """Plot barchart of mean absolute shap value.
        
        Displays all individual shap value for each feature in a horizontal
        scatter chart in descending order by mean absolute shap value.

        Args:
          topx(int, optional): Only display topx most important features, defaults to None
          cats(bool, optional): Group categoricals , defaults to False
          pos_label: positive class (Default value = None)

        Returns:
          plotly.Fig

        """
        if cats:
            return plotly_shap_scatter_plot(
                                self.shap_values_cats(pos_label),
                                self.X_cats,
                                self.importances_df(kind='shap', topx=topx, cats=True, pos_label=pos_label)\
                                        ['Feature'].values.tolist())
        else:
            return plotly_shap_scatter_plot(
                                self.shap_values(pos_label),
                                self.X,
                                self.importances_df(kind='shap', topx=topx, cats=False, pos_label=pos_label)\
                                        ['Feature'].values.tolist())

    def plot_shap_interaction_summary(self, col, topx=None, cats=False, pos_label=None):
        """Plot barchart of mean absolute shap interaction values
        
        Displays all individual shap interaction values for each feature in a
        horizontal scatter chart in descending order by mean absolute shap value.

        Args:
          col(type]): feature for which to show interactions summary
          topx(int, optional): only show topx most important features, defaults to None
          cats:  group categorical features (Default value = False)
          pos_label: positive class (Default value = None)

        Returns:
          fig

        """
        if col in self.cats:
            cats = True
        interact_cols = self.shap_top_interactions(col, cats=cats, pos_label=pos_label)
        if topx is None: topx = len(interact_cols)

        return plotly_shap_scatter_plot(
                self.shap_interaction_values_by_col(col, cats=cats, pos_label=pos_label),
                self.X_cats if cats else self.X, interact_cols[:topx])

    def plot_shap_dependence(self, col, color_col=None, highlight_idx=None,pos_label=None):
        """plot shap dependence
        
        Plots a shap dependence plot:
            - on the x axis the possible values of the feature `col`
            - on the y axis the associated individual shap values

        Args:
          col(str): feature to be displayed
          color_col(str): if color_col provided then shap values colored (blue-red) 
                    according to feature color_col (Default value = None)
          highlight_idx: individual observation to be highlighed in the plot. 
                    (Default value = None)
          pos_label: positive class (Default value = None)

        Returns:

        """
        cats = self.check_cats(col, color_col)
        if cats:
            if col in self.cats:
                return plotly_shap_violin_plot(self.X_cats, self.shap_values_cats(pos_label), col, color_col)
            else:
                return plotly_dependence_plot(self.X_cats, self.shap_values_cats(pos_label),
                                                col, color_col,
                                                highlight_idx=highlight_idx,
                                                na_fill=self.na_fill)
        else:
            return plotly_dependence_plot(self.X, self.shap_values(pos_label),
                                            col, color_col,
                                            highlight_idx=highlight_idx,
                                            na_fill=self.na_fill)

    def plot_shap_interaction(self, col, interact_col, highlight_idx=None, 
                                pos_label=None):
        """plots a dependence plot for shap interaction effects

        Args:
          col(str): feature for which to find interaction values
          interact_col(str): feature for which interaction value are displayed
          highlight_idx(int, optional, optional): idx that will be highlighted, defaults to None
          pos_label:  (Default value = None)

        Returns:
          plotly.Fig: Plotly Fig

        """
        cats = self.check_cats(col, interact_col)
        if cats and interact_col in self.cats:
            return plotly_shap_violin_plot(
                self.X_cats, 
                self.shap_interaction_values_by_col(col, cats, pos_label=pos_label),
                interact_col, col, interaction=True)
        else:
            return plotly_dependence_plot(self.X_cats if cats else self.X,
                self.shap_interaction_values_by_col(col, cats, pos_label=pos_label),
                interact_col, col, highlight_idx=highlight_idx,
                interaction=True)

    def plot_pdp(self, col, index=None, drop_na=True, sample=100,
                    gridlines=100, gridpoints=10, pos_label=None):
        """plot partial dependence plot (pdp)
        
        returns plotly fig for a partial dependence plot showing ice lines
        for num_grid_lines rows, average pdp based on sample of sample.
        If index is given, display pdp for this specific index.

        Args:
          col(str): feature to display pdp graph for
          index(int or str, optional, optional): index to highlight in pdp graph, 
                    defaults to None
          drop_na(bool, optional, optional): if true drop samples with value 
                    equal to na_fill, defaults to True
          sample(int, optional, optional): sample size on which the average 
                    pdp will be calculated, defaults to 100
          gridlines(int, optional): number of ice lines to display, 
                    defaults to 100
          gridpoints(ints: int, optional): number of points on the x axis 
                    to calculate the pdp for, defaults to 10
          pos_label:  (Default value = None)

        Returns:
          plotly.Fig: fig

        """
        pdp_result = self.get_pdp_result(col, index,
                            drop_na=drop_na, sample=sample,
                            num_grid_points=gridpoints)

        if index is not None:
            try:
                col_value, pred = self.get_col_value_plus_prediction(index, col)
                return plotly_pdp(pdp_result,
                                display_index=0, # the idx to be displayed is always set to the first row by self.get_pdp_result()
                                index_feature_value=col_value, index_prediction=pred,
                                feature_name=col,
                                num_grid_lines=min(gridlines, sample, len(self.X)))
            except:
                return plotly_pdp(pdp_result, feature_name=col,
                        num_grid_lines=min(gridlines, sample, len(self.X)))
        else:
            return plotly_pdp(pdp_result, feature_name=col,
                        num_grid_lines=min(gridlines, sample, len(self.X)))



class ClassifierExplainer(BaseExplainer):
    """ """
    def __init__(self, model,  X, y=None,  permutation_metric=roc_auc_score, 
                    shap='guess', X_background=None, model_output="probability",
                    cats=None, idxs=None, descriptions=None,
                    permutation_cv=None, na_fill=-999,
                    labels=None, pos_label=1):
        """
        Explainer for classification models. Defines the shap values for
        each possible class in the classification.

        You assign the positive label class afterwards with e.g. explainer.pos_label=0

        In addition defines a number of plots specific to classification problems
        such as a precision plot, confusion matrix, roc auc curve and pr auc curve.

        Compared to BaseExplainer defines two additional parameters

        Args:
            labels(list): list of str labels for the different classes, 
                        defaults to e.g. ['0', '1'] for a binary classification
            pos_label: class that should be used as the positive class, 
                        defaults to 1
        """
        super().__init__(model, X, y, permutation_metric, 
                            shap, X_background, model_output, 
                            cats, idxs, descriptions, permutation_cv, na_fill)

        if labels is not None:
            self.labels = labels
        elif hasattr(self.model, 'classes_'):
                self.labels =  [str(cls) for cls in self.model.classes_]
        else:
            self.labels = [str(i) for i in range(self.y.nunique())]
        self.pos_label = pos_label
        self.is_classifier = True

    @property
    def shap_explainer(self):
        """Initialize SHAP explainer. 
        
        Taking into account model type and model_output
        """
        if not hasattr(self, '_shap_explainer'):
            model_str = str(type(self.model)).replace("'", "").replace("<", "").replace(">", "").split(".")[-1]
            if self.shap == 'tree':
                if (str(type(self.model)).endswith("XGBClassifier'>") or
                    str(type(self.model)).endswith("LGBMClassifier'>") or
                    str(type(self.model)).endswith("CatBoostClassifier'>") or
                    str(type(self.model)).endswith("GradientBoostingClassifier'>") or
                    str(type(self.model)).endswith("HistGradientBoostingClassifier'>")
                    ):
                    
                    if self.model_output == "probability": 
                        if self.X_background is None:
                            print(
                                f"Note: model_output=='probability'. For {model_str} shap values normally get "
                                "calculated against X_background, but paramater X_background=None, "
                                "so using X instead")
                        print("Generating self.shap_explainer = shap.TreeExplainer(model, "
                             f"{'X_background' if self.X_background is not None else 'X'}"
                             ", model_output='probability', feature_perturbation='interventional')...")
                        print("Note: Shap interaction values will not be available. "
                              "If shap values in probability space are not necessary you can "
                              "pass model_output='logodds' to get shap values in logodds without the need for "
                              "a background dataset and also working shap interaction values...")
                        self._shap_explainer = shap.TreeExplainer(
                                                    self.model, 
                                                    self.X_background if self.X_background is not None else self.X,
                                                    model_output="probability",
                                                    feature_perturbation="interventional")
                        self.interactions_should_work = False
                    else:
                        self.model_output = "logodds"
                        print(f"Generating self.shap_explainer = shap.TreeExplainer(model{', X_background' if self.X_background is not None else ''})")
                        self._shap_explainer = shap.TreeExplainer(self.model, self.X_background)
                else:
                    if self.model_output == "probability":
                        print(f"Note: model_output=='probability', so assuming that raw shap output of {model_str} is in probability space...")
                    print(f"Generating self.shap_explainer = shap.TreeExplainer(model{', X_background' if self.X_background is not None else ''})")
                    self._shap_explainer = shap.TreeExplainer(self.model, self.X_background)


            elif self.shap=='linear':
                if self.model_output == "probability":
                    print(
                        "Note: model_output='probability' is currently not supported for linear classifiers "
                        "models with shap. So defaulting to model_output='logodds' "
                        "If you really need probability outputs use shap='kernel' instead."
                    )
                    self.model_output = "logodds"
                if self.X_background is None:
                    print(
                        "Note: shap values for shap='linear' get calculated against "
                        "X_background, but paramater X_background=None, so using X instead...")
                print("Generating self.shap_explainer = shap.LinearExplainer(model, "
                             f"{'X_background' if self.X_background is not None else 'X'})...")
                
                self._shap_explainer = shap.LinearExplainer(self.model, 
                                            self.X_background if self.X_background is not None else self.X)
            elif self.shap=='deep':
                print("Generating self.shap_explainer = shap.DeepExplainer(model{', X_background' if self.X_background is not None else ''})")
                self._shap_explainer = shap.DeepExplainer(self.model, self.X_background)
            elif self.shap=='kernel': 
                if self.X_background is None:
                    print(
                        "Note: shap values for shap='kernel' normally get calculated against "
                        "X_background, but paramater X_background=None, so using X instead...")
                if self.model_output != "probability":
                    print(
                        "Note: for ClassifierExplainer shap='kernel' defaults to model_output='probability"
                    )
                    self.model_output = 'probability'
                print("Generating self.shap_explainer = shap.KernelExplainer(model, "
                             f"{'X_background' if self.X_background is not None else 'X'}"
                             ", link='identity')")
                self._shap_explainer = shap.KernelExplainer(model.predict_proba, 
                                            self.X_background if self.X_background is not None else self.X,
                                            link="identity")
            print("Final note: You can always monkeypatch self.shap_explainer if desired...")
               
        return self._shap_explainer

    @property
    def pos_label(self):
        return self._pos_label

    @pos_label.setter
    def pos_label(self, label):
        if isinstance(label, int) and label >=0 and label <len(self.labels):
            self._pos_label = label
        elif isinstance(label, str) and label in self.labels:
            self._pos_label = self.labels.index(label)
        else:
            raise ValueError(f"'{label}' not in labels")

    @property
    def pos_label_str(self):
        """return str label of self.pos_label"""
        return self.labels[self.pos_label]

    def get_pos_label_index(self, pos_label_str):
        """return int index of pos_label_str"""
        assert pos_label_str in self.labels, \
            f"Unknown pos_label. {pos_label_str} not in self.labels!" 
        return self.labels.index(pos_label_str)

    def get_prop_for_label(self, prop:str, label):
        """return property for a specific pos_label

        Args:
          prop: property to get for a certain pos_label
          label: pos_label

        Returns:
            property
        """
        tmp = self.pos_label
        self.pos_label = label
        ret = getattr(self, prop)
        self.pos_label = tmp
        return ret

    @property
    def y_binary(self):
        """for multiclass problems returns one-vs-rest array of [1,0] pos_label"""
        if not hasattr(self, '_y_binaries'):
            self._y_binaries = [np.where(self.y.values==i, 1, 0)
                        for i in range(self.y.nunique())]
        return default_list(self._y_binaries, self.pos_label)

    @property
    def pred_probas_raw(self):
        """returns pred_probas with probability for each class"""
        if not hasattr(self, '_pred_probas'):
            print("Calculating prediction probabilities...")
            assert hasattr(self.model, 'predict_proba'), \
                "model does not have a predict_proba method!"
            self._pred_probas =  self.model.predict_proba(self.X)
        return self._pred_probas

    @property
    def pred_percentiles_raw(self):
        """ """
        if not hasattr(self, '_pred_percentiles_raw'):
            print("Calculating pred_percentiles...")
            self._pred_percentiles_raw = (pd.DataFrame(self.pred_probas_raw)
                                .rank(method='min')
                                .divide(len(self.pred_probas_raw))
                                .values)
        return self._pred_percentiles_raw

    @property
    def pred_probas(self):
        """returns pred_proba for pos_label class"""
        return default_2darray(self.pred_probas_raw, self.pos_label)

    @property
    def pred_percentiles(self):
        """returns ranks for pos_label class"""
        return default_2darray(self.pred_percentiles_raw, self.pos_label)

    @property
    def permutation_importances(self):
        """Permutation importances"""
        if not hasattr(self, '_perm_imps'):
            print("Calculating importances...")
            self._perm_imps = [cv_permutation_importances(
                            self.model, self.X, self.y, self.metric,
                            cv=self.permutation_cv,
                            needs_proba=self.is_classifier,
                            pos_label=label) for label in range(len(self.labels))]
        return default_list(self._perm_imps, self.pos_label)

    @property
    def permutation_importances_cats(self):
        """permutation importances with categoricals grouped"""
        if not hasattr(self, '_perm_imps_cats'):
            self._perm_imps_cats = [cv_permutation_importances(
                            self.model, self.X, self.y, self.metric, self.cats,
                            cv=self.permutation_cv,
                            needs_proba=self.is_classifier,
                            pos_label=label) for label in range(len(self.labels))]
        return default_list(self._perm_imps_cats, self.pos_label)

    @property
    def shap_base_value(self):
        """SHAP base value: average outcome of population"""
        if not hasattr(self, '_shap_base_value'):
            _ = self.shap_values() # CatBoost needs to have shap values calculated before expected value for some reason
            self._shap_base_value = self.shap_explainer.expected_value
            if isinstance(self._shap_base_value, np.ndarray) and len(self._shap_base_value) == 1:
                self._shap_base_value = self._shap_base_value[0]
            if isinstance(self._shap_base_value, np.ndarray):
                self._shap_base_value = list(self._shap_base_value)
            if len(self.labels)==2 and isinstance(self._shap_base_value, (np.floating, float)):
                if self.model_output == 'probability':
                    assert self._shap_base_value >= 0.0 and self._shap_base_value <= 1.0, \
                        (f"Shap base value does not look like a probability: {self._shap_base_value}. "
                         "Try setting model_output='logodds'.")
                    self._shap_base_value = [1-self._shap_base_value, self._shap_base_value]
                else: # assume logodds
                    self._shap_base_value = [-self._shap_base_value, self._shap_base_value]
            assert len(self._shap_base_value)==len(self.labels),\
                f"len(shap_explainer.expected_value)={len(self._shap_base_value)}"\
                 + f"and len(labels)={len(self.labels)} do not match!"
        return default_list(self._shap_base_value, self.pos_label)

    @property
    def shap_values(self):
        """SHAP Values"""
        if not hasattr(self, '_shap_values'):
            print("Calculating shap values...")
            self._shap_values = self.shap_explainer.shap_values(self.X)
            
            if not isinstance(self._shap_values, list) and len(self.labels)==2:
                if self.model_output=='probability':
                    self._shap_values = [1-self._shap_values, self._shap_values]
                else: #assume logodds
                    self._shap_values = [-self._shap_values, self._shap_values]

            assert len(self._shap_values)==len(self.labels),\
                f"len(shap_values)={len(self._shap_values)}"\
                + f"and len(labels)={len(self.labels)} do not match!"
        return default_list(self._shap_values, self.pos_label)

    @property
    def shap_values_cats(self):
        """SHAP values with categoricals grouped together"""
        if not hasattr(self, '_shap_values_cats'):
            _ = self.shap_values
            self._shap_values_cats = [
                    merge_categorical_shap_values(
                        self.X, sv, self.cats) for sv in self._shap_values]
            
        return default_list(self._shap_values_cats, self.pos_label)


    @property
    def shap_interaction_values(self):
        """SHAP interaction values"""
        if not hasattr(self, '_shap_interaction_values'):
            print("Calculating shap interaction values...")
            _ = self.shap_values #make sure shap values have been calculated
            self._shap_interaction_values = self.shap_explainer.shap_interaction_values(self.X)
            
            if not isinstance(self._shap_interaction_values, list) and len(self.labels)==2:
                if self.model_output == "probability":
                    self._shap_interaction_values = [1-self._shap_interaction_values,
                                                        self._shap_interaction_values]
                else: # assume logodds so logodds of negative class is -logodds of positive class
                    self._shap_interaction_values = [-self._shap_interaction_values,
                                                        self._shap_interaction_values]

            self._shap_interaction_values = [
                normalize_shap_interaction_values(siv, self.shap_values)
                    for siv, sv in zip(self._shap_interaction_values, self._shap_values)]
        return default_list(self._shap_interaction_values, self.pos_label)

    @property
    def shap_interaction_values_cats(self):
        """SHAP interaction values with categoricals grouped together"""
        if not hasattr(self, '_shap_interaction_values_cats'):
            _ = self.shap_interaction_values
            self._shap_interaction_values_cats = [
                merge_categorical_shap_interaction_values(
                    self.X, self.X_cats, siv) for siv in self._shap_interaction_values]
        return default_list(self._shap_interaction_values_cats, self.pos_label)

    @property
    def mean_abs_shap(self):
        """mean absolute SHAP values"""
        if not hasattr(self, '_mean_abs_shap'):
            _ = self.shap_values
            self._mean_abs_shap = [mean_absolute_shap_values(
                                self.columns, sv) for sv in self._shap_values]
        return default_list(self._mean_abs_shap, self.pos_label)

    @property
    def mean_abs_shap_cats(self):
        """mean absolute SHAP values with categoricals grouped together"""
        if not hasattr(self, '_mean_abs_shap_cats'):
            _ = self.shap_values
            self._mean_abs_shap_cats = [mean_absolute_shap_values(
                                self.columns, sv, self.cats) for sv in self._shap_values]
        return default_list(self._mean_abs_shap_cats, self.pos_label)

    def cutoff_from_percentile(self, percentile, pos_label=None):
        """The cutoff equivalent to the percentile given

        For example if you want the cutoff that splits the highest 20% 
        pred_proba from the lowest 80%, you would set percentile=0.8 
        and get the correct cutoff.

        Args:
          percentile(float):  percentile to convert to cutoff 
          pos_label: positive class (Default value = None)

        Returns:
          cutoff

        """
        if pos_label is None:
            return pd.Series(self.pred_probas).nlargest(int((1-percentile)*len(self))).min()
        else:
            return pd.Series(self.pred_probas_raw[:, pos_label]).nlargest(int((1-percentile)*len(self))).min()

    def metrics(self, cutoff=0.5, pos_label=None):
        """returns a dict with useful metrics for your classifier:
        
        accuracy, precision, recall, f1, roc auc, pr auc, log loss

        Args:
          cutoff(float): cutoff used to calculate metrics (Default value = 0.5)
          pos_label: positive class (Default value = None)

        Returns:
          dict

        """
        if pos_label is None: pos_label = self.pos_label
        metrics_dict = {
            'accuracy' : accuracy_score(self.y_binary(pos_label), np.where(self.pred_probas(pos_label) > cutoff, 1, 0)),
            'precision' : precision_score(self.y_binary(pos_label), np.where(self.pred_probas(pos_label) > cutoff, 1, 0)),
            'recall' : recall_score(self.y_binary(pos_label), np.where(self.pred_probas(pos_label) > cutoff, 1, 0)),
            'f1' : f1_score(self.y_binary(pos_label), np.where(self.pred_probas(pos_label) > cutoff, 1, 0)),
            'roc_auc_score' : roc_auc_score(self.y_binary(pos_label), self.pred_probas(pos_label)),
            'pr_auc_score' : average_precision_score(self.y_binary(pos_label), self.pred_probas(pos_label)),
            'log_loss' : log_loss(self.y_binary(pos_label), self.pred_probas(pos_label))
        }
        return metrics_dict

    def get_pdp_result(self, col, index=None, drop_na=True,
                        sample=1000, num_grid_points=20, pos_label=None):
        """gets a the result out of the PDPBox library
        
        Adjust for multiple labels.

        Args:
          col(str): Feature to display 
          index(str or int): index to add to plot (Default value = None)
          drop_na(bool): drop value equal to self.fill_na  (Default value = True)
          sample(int): sample size to compute average pdp  (Default value = 1000)
          num_grid_points(int): number of horizontal breakpoints in pdp (Default value = 20)
          pos_label: positive class  (Default value = None)

        Returns:
          PDPBox pdp result

        """
        if pos_label is None: pos_label = self.pos_label
        pdp_result = super().get_pdp_result(
                                col, index, drop_na, sample, num_grid_points)
        if len(self.labels)==2:
            # for binary classifer PDPBox only gives pdp for the positive class.
            # instead of a list of pdps for every class
            # so we simply inverse when predicting the negative class
            if pos_label==0:
                pdp_result.pdp = 1 - pdp_result.pdp
                pdp_result.ice_lines = 1 - pdp_result.ice_lines
            return pdp_result
        else:
             return pdp_result[pos_label]

    def random_index(self, y_values=None, return_str=False,
                    pred_proba_min=None, pred_proba_max=None,
                    pred_percentile_min=None, pred_percentile_max=None, pos_label=None):
        """random index satisfying various constraint

        Args:
          y_values: list of labels to include (Default value = None)
          return_str: return str from self.idxs (Default value = False)
          pred_proba_min: minimum pred_proba (Default value = None)
          pred_proba_max: maximum pred_proba (Default value = None)
          pred_percentile_min: minimum pred_proba percentile (Default value = None)
          pred_percentile_max: maximum pred_proba percentile (Default value = None)
          pos_label: positive class (Default value = None)

        Returns:
          index

        """
       # if pos_label is None: pos_label = self.pos_label
        if (y_values is None 
            and pred_proba_min is None and pred_proba_max is None
            and pred_percentile_min is None and pred_percentile_max is None):
            potential_idxs = self.y.index
        else:
            if y_values is None: y_values = self.y.unique().tolist()
            if not isinstance(y_values, list): y_values = [y_values]
            y_values = [y if isinstance(y, int) else self.labels.index(y) for y in y_values]
            if pred_proba_min is None: pred_proba_min = self.pred_probas(pos_label).min()
            if pred_proba_max is None: pred_proba_max = self.pred_probas(pos_label).max()
            if pred_percentile_min is None: pred_percentile_min = 0.0
            if pred_percentile_max is None: pred_percentile_max = 1.0
            
            potential_idxs = self.y[(self.y.isin(y_values)) &
                            (self.pred_probas(pos_label) >= pred_proba_min) &
                            (self.pred_probas(pos_label) <= pred_proba_max) &
                            (self.pred_percentiles(pos_label) > pred_percentile_min) &
                            (self.pred_percentiles(pos_label) <= pred_percentile_max)].index
        if not potential_idxs.empty:
            idx = np.random.choice(potential_idxs)
        else:
            return None
        if return_str:
            assert self.idxs is not None, \
                "no self.idxs property found..."
            return self.idxs[idx]
        return int(idx)

    def contrib_summary_df(self, index, cats=True, topx=None, cutoff=None, 
                            round=2, pos_label=None):
        """Takes a contrib_df, and formats it to a more human readable format

        Args:
          index: 
          cats:  group categorical columns together(Default value = True)
          topx:  only show topx highest shap values(Default value = None)
          cutoff:  only show shap values above cutoff(Default value = None)
          round:  round shapvalues to round digits (Default value = 2)
          pos_label: show shap value for positive class pos_label (Default value = None)

        Returns:
          pd.DataFrame

        """
        idx = self.get_int_idx(index) # if passed str convert to int index
        return get_contrib_summary_df(self.contrib_df(idx, cats, topx, cutoff, pos_label), 
                                            model_output = self.model_output, round=round)

    def precision_df(self, bin_size=None, quantiles=None, multiclass=False, 
                        round=3, pos_label=None):
        """dataframe with predicted probabilities and precision

        Args:
          bin_size(float, optional, optional): group predictions in bins of size bin_size, defaults to 0.1
          quantiles(int, optional, optional): group predictions in evenly sized quantiles of size quantiles, defaults to None
          multiclass(bool, optional, optional): whether to calculate precision for every class (Default value = False)
          round:  (Default value = 3)
          pos_label:  (Default value = None)

        Returns:
          pd.DataFrame: precision_df

        """
        assert self.pred_probas is not None

        if pos_label is None: pos_label = self.pos_label

        if bin_size is None and quantiles is None:
            bin_size=0.1 # defaults to bin_size=0.1
        if multiclass:
            return get_precision_df(self.pred_probas_raw, self.y,
                                bin_size, quantiles, 
                                round=round, pos_label=pos_label)
        else:
            return get_precision_df(self.pred_probas(pos_label), self.y_binary(pos_label), 
                                    bin_size, quantiles, round=round)

    def lift_curve_df(self, pos_label=None):
        """returns a pd.DataFrame with data needed to build a lift curve

        Args:
          pos_label:  (Default value = None)

        Returns:

        """
        if pos_label is None: pos_label = self.pos_label
        return get_lift_curve_df(self.pred_probas(pos_label), self.y, pos_label)

    def prediction_result_markdown(self, index, include_percentile=True, round=2, pos_label=None):
        """markdown of result of prediction for index

        Args:
          index(int or str): the index of the row for which to generate the prediction
          include_percentile(bool, optional, optional): include the rank 
                    percentile of the prediction, defaults to True
          round(int, optional, optional): rounding to apply to results, defaults to 2
          pos_label:  (Default value = None)
          **kwargs: 

        Returns:
          str: markdown string

        """
        int_idx = self.get_int_idx(index)
        if pos_label is None: pos_label = self.pos_label
        
        def display_probas(pred_probas_raw, labels, model_output='probability', round=2):
            assert (len(pred_probas_raw.shape)==1 and len(pred_probas_raw) ==len(labels))
            def log_odds(p, round=2):
                return np.round(np.log(p / (1-p)), round)
            for i in range(len(labels)):
                proba_str = f"{np.round(100*pred_probas_raw[i], round)}%"
                logodds_str = f"(logodds={log_odds(pred_probas_raw[i], round)})"
                yield f"* {labels[i]}: {proba_str if model_output=='probability' else logodds_str}\n"

        model_prediction = ""
        if (isinstance(self.y[0], int) or 
            isinstance(self.y[0], np.int64)):
            model_prediction += f"Outcome: {self.labels[self.y[int_idx]]}\n\n"
        
        model_prediction += "Prediction probabilities per label:\n\n" 
        for pred in display_probas(
                self.pred_probas_raw[int_idx], 
                self.labels, self.model_output, round):
            model_prediction += pred
        
        if include_percentile:
            percentile = np.round(100*(1-self.pred_percentiles(pos_label)[int_idx]))
            model_prediction += f'\nIn top {percentile}% percentile probability {self.labels[pos_label]}'      
        return model_prediction


    def plot_precision(self, bin_size=None, quantiles=None, cutoff=None, multiclass=False, pos_label=None):
        """plot precision vs predicted probability
        
        plots predicted probability on the x-axis and observed precision (fraction of actual positive
        cases) on the y-axis.
        
        Should pass either bin_size fraction of number of quantiles, but not both.

        Args:
          bin_size(float, optional):  size of the bins on x-axis (e.g. 0.05 for 20 bins)
          quantiles(int, optional): number of equal sized quantiles to split 
                    the predictions by e.g. 20, optional)
          cutoff: cutoff of model to include in the plot (Default value = None)
          multiclass: whether to display all classes or only positive class, 
                    defaults to False
          pos_label: positive label to display, defaults to self.pos_label

        Returns:
          Plotly fig

        """
        if pos_label is None: pos_label = self.pos_label
        if bin_size is None and quantiles is None:
            bin_size=0.1 # defaults to bin_size=0.1
        precision_df = self.precision_df(
                bin_size=bin_size, quantiles=quantiles, multiclass=multiclass, pos_label=pos_label)
        return plotly_precision_plot(precision_df,
                    cutoff=cutoff, labels=self.labels, pos_label=pos_label)

    def plot_cumulative_precision(self, pos_label=None):
        """plot cumulative precision
        
        returns a cumulative precision plot, which is a slightly different
        representation of a lift curve.

        Args:
          pos_label: positive label to display, defaults to self.pos_label

        Returns:
          plotly fig

        """
        if pos_label is None: pos_label = self.pos_label
        return plotly_cumulative_precision_plot(
                    self.lift_curve_df(pos_label=pos_label), self.labels, pos_label)

    def plot_confusion_matrix(self, cutoff=0.5, normalized=False, binary=False, pos_label=None):
        """plot of a confusion matrix.

        Args:
          cutoff(float, optional, optional): cutoff of positive class to 
                    calculate confusion matrix for, defaults to 0.5
          normalized(bool, optional, optional): display percentages instead 
                    of counts , defaults to False
          binary(bool, optional, optional): if multiclass display one-vs-rest 
                    instead, defaults to False
          pos_label: positive label to display, defaults to self.pos_label

        Returns:
          plotly fig

        """
        if pos_label is None: pos_label = self.pos_label
        pos_label_str = self.labels[pos_label]

        if binary:
            if len(self.labels)==2:
                def order_binary_labels(labels, pos_label):
                    pos_index = labels.index(pos_label)
                    return [labels[1-pos_index], labels[pos_index]]
                labels = order_binary_labels(self.labels, pos_label_str)
            else:
                labels = ['Not ' + pos_label_str, pos_label_str]

            return plotly_confusion_matrix(
                    self.y_binary(pos_label), np.where(self.pred_probas(pos_label) > cutoff, 1, 0),
                    normalized=normalized, labels=labels)
        else:
            return plotly_confusion_matrix(
                self.y, self.pred_probas_raw.argmax(axis=1),
                normalized=normalized, labels=self.labels)

    def plot_lift_curve(self, cutoff=None, percentage=False, round=2, pos_label=None):
        """plot of a lift curve.

        Args:
          cutoff(float, optional): cutoff of positive class to calculate lift 
                    (Default value = None)
          percentage(bool, optional): display percentages instead of counts, 
                    defaults to False
          round: number of digits to round to (Default value = 2)
          pos_label: positive label to display, defaults to self.pos_label

        Returns:
          plotly fig

        """
        return plotly_lift_curve(self.lift_curve_df(pos_label), cutoff, percentage, round)

    def plot_classification(self, cutoff=0.5, percentage=True, pos_label=None):
        """plot showing a barchart of the classification result for cutoff

        Args:
          cutoff(float, optional): cutoff of positive class to calculate lift 
                    (Default value = 0.5)
          percentage(bool, optional): display percentages instead of counts, 
                    defaults to True
          pos_label: positive label to display, defaults to self.pos_label

        Returns:
          plotly fig

        """
        return plotly_classification_plot(self.pred_probas(pos_label), self.y, self.labels, cutoff, percentage=percentage)

    def plot_roc_auc(self, cutoff=0.5, pos_label=None):
        """plots ROC_AUC curve.
        
        The TPR and FPR of a particular cutoff is displayed in crosshairs.

        Args:
          cutoff: cutoff value to be included in plot (Default value = 0.5)
          pos_label:  (Default value = None)

        Returns:

        """
        return plotly_roc_auc_curve(self.y_binary(pos_label), self.pred_probas(pos_label), cutoff=cutoff)

    def plot_pr_auc(self, cutoff=0.5, pos_label=None):
        """plots PR_AUC curve.
        
        the precision and recall of particular cutoff is displayed in crosshairs.

        Args:
          cutoff: cutoff value to be included in plot (Default value = 0.5)
          pos_label:  (Default value = None)

        Returns:

        """
        return plotly_pr_auc_curve(self.y_binary(pos_label), self.pred_probas(pos_label), cutoff=cutoff)

    def calculate_properties(self, include_interactions=True):
        """calculate all lazily calculated properties of explainer

        Args:
          include_interactions:  (Default value = True)

        Returns:
            None

        """
        _ = self.pred_probas
        super().calculate_properties(include_interactions=include_interactions)


class RegressionExplainer(BaseExplainer):
    """ """
    def __init__(self, model,  X, y=None, permutation_metric=r2_score, 
                    shap="guess", X_background=None, model_output="raw",
                    cats=None, idxs=None, descriptions=None, 
                    permutation_cv=None, na_fill=-999,
                    units=""):
        """Explainer for regression models.

        In addition to BaseExplainer defines a number of plots specific to 
        regression problems such as a predicted vs actual and residual plots.

        Combared to BaseExplainerBunch defines two additional parameters.

        Args:
          units(str): units to display for regression quantity
        """
        super().__init__(model, X, y, permutation_metric, 
                            shap, X_background, model_output,
                            cats, idxs, descriptions, permutation_cv, na_fill)
        self.units = units
        self.is_regression = True
    
    @property
    def residuals(self):
        """residuals: y-preds"""
        if not hasattr(self, '_residuals'):
            print("Calculating residuals...")
            self._residuals =  self.y-self.preds
        return self._residuals

    @property
    def abs_residuals(self):
        """absolute residuals"""
        if not hasattr(self, '_abs_residuals'):
            print("Calculating absolute residuals...")
            self._abs_residuals =  np.abs(self.residuals)
        return self._abs_residuals

    def random_index(self, y_min=None, y_max=None, pred_min=None, pred_max=None, 
                        residuals_min=None, residuals_max=None,
                        abs_residuals_min=None, abs_residuals_max=None,
                        return_str=False, **kwargs):
        """random index following to various exclusion criteria

        Args:
          y_min:  (Default value = None)
          y_max:  (Default value = None)
          pred_min:  (Default value = None)
          pred_max:  (Default value = None)
          residuals_min:  (Default value = None)
          residuals_max:  (Default value = None)
          abs_residuals_min:  (Default value = None)
          abs_residuals_max:  (Default value = None)
          return_str:  return the str index from self.idxs (Default value = False)
          **kwargs: 

        Returns:
          a random index that fits the exclusion criteria

        """
        if y_min is None:
            y_min = self.y.min()
        if y_max is None:
            y_max = self.y.max()
        if pred_min is None:
            pred_min = self.preds.min()
        if pred_max is None:
            pred_max = self.preds.max()
        if residuals_min is None:
            residuals_min = self.residuals.min()
        if residuals_max is None:
            residuals_max = self.residuals.max()
        if abs_residuals_min is None:
            abs_residuals_min = self.abs_residuals.min()
        if abs_residuals_max is None:
            abs_residuals_max = self.abs_residuals.max()

        potential_idxs = self.y[(self.y >= y_min) & 
                                (self.y <= y_max) & 
                                (self.preds >= pred_min) & 
                                (self.preds <= pred_max) &
                                (self.residuals >= residuals_min) & 
                                (self.residuals <= residuals_max) &
                                (self.abs_residuals >= abs_residuals_min) & 
                                (self.abs_residuals <= abs_residuals_max)].index

        if len(potential_idxs) > 0:
            idx = np.random.choice(potential_idxs)
        else:
            return None
        if return_str:
            assert self.idxs is not None, \
                "no self.idxs property found..."
            return self.idxs[idx]
        return int(idx)

    def prediction_result_markdown(self, index, round=2, **kwargs):
        """markdown of prediction result

        Args:
          index: row index to be predicted
          round:  (Default value = 2)
          **kwargs: 

        Returns:
          dict

        """
        int_idx = self.get_int_idx(index)
        model_prediction = f"Prediction: {np.round(self.preds[int_idx], round)}\n\n"
        model_prediction += f"Actual Outcome: {np.round(self.y[int_idx], round)}\n\n"
        model_prediction += f"Residual: {np.round(self.residuals[int_idx], round)}"

        return model_prediction

    def metrics(self):
        """dict of performance metrics: rmse, mae and R^2"""
        metrics_dict = {
            'rmse' : np.sqrt(mean_squared_error(self.y, self.preds)),
            'mae' : mean_absolute_error(self.y, self.preds),
            'R2' : r2_score(self.y, self.preds),
        }
        return metrics_dict

    def plot_predicted_vs_actual(self, round=2, logs=False, **kwargs):
        """plot with predicted value on x-axis and actual value on y axis.

        Args:
          round(int, optional): rounding to apply to outcome, defaults to 2
          logs(bool, optional): whether to take logs of predicted and actual value, defaults to False
          **kwargs: 

        Returns:
          Plotly fig

        """
        return plotly_predicted_vs_actual(self.y, self.preds, units=self.units, round=round, logs=logs)
    
    def plot_residuals(self, vs_actual=False, round=2, ratio=False, **kwargs):
        """plot of residuals. x-axis is the predicted outcome by default

        Args:
          vs_actual(bool, optional): use actual value for x-axis,   
                    defaults to False
          round(int, optional): rounding to perform on values, defaults to 2
          ratio(bool, optional): whether to take the residual/prediction 
                    ratio instead, defaults to False
          **kwargs: 

        Returns:
          Plotly fig

        """
        return plotly_plot_residuals(self.y, self.preds, 
                                     vs_actual=vs_actual, units=self.units, round=round, ratio=ratio)
    
    def plot_residuals_vs_feature(self, col, ratio=False, round=2, dropna=True, **kwargs):
        """Plot residuals vs individual features

        Args:
          col(str): Plot against feature col
          ratio(bool, optional): display residual ratio instead of raw value, 
                    defaults to False
          round(int, optional: rounding to perform on residuals, defaults to 2
          dropna(bool, optional: drop missing values from plot, defaults to True
          **kwargs: 

        Returns:
          plotly fig

        """
        assert col in self.columns, \
            f'{col} not in columns!'
        na_mask = self.X[col] != self.na_fill if dropna else np.array([True]*len(self.X))
        return plotly_residuals_vs_col(self.y[na_mask], self.preds[na_mask], self.X[col][na_mask], 
                                       ratio=ratio, units=self.units, round=round)


class RandomForestExplainer(BaseExplainer):
    """RandomForestBunch allows for the analysis of individual DecisionTrees that
    make up the RandomForest.

    """
    
    @property
    def no_of_trees(self):
        """The number of trees in the RandomForest model"""
        return len(self.model.estimators_)
        
    @property
    def graphviz_available(self):
        """ """
        if not hasattr(self, '_graphviz_available'):
            try:
                import graphviz.backend as be
                cmd = ["dot", "-V"]
                stdout, stderr = be.run(cmd, capture_output=True, check=True, quiet=True)
            except:
                print("""
                WARNING: you don't seem to have graphviz in your path (cannot run 'dot -V'), 
                so no dtreeviz visualisation of decision trees will be shown on the shadow trees tab.

                See https://github.com/parrt/dtreeviz for info on how to properly install graphviz 
                for dtreeviz. 
                """)
                self._graphviz_available = False
            else:
                self._graphviz_available = True
        return self._graphviz_available

    @property
    def decision_trees(self):
        """a list of ShadowDecTree objects"""
        if not hasattr(self, '_decision_trees'):
            print("Generating ShadowDecTree for each individual decision tree...")
            self._decision_trees = get_decision_trees(self.model, self.X, self.y)
        return self._decision_trees

    def decisiontree_df(self, tree_idx, index, pos_label=None):
        """dataframe with all decision nodes of a particular decision tree

        Args:
          tree_idx: the n'th tree in the random forest
          index: row index
          round:  (Default value = 2)
          pos_label:  positive class (Default value = None)

        Returns:
          dataframe with summary of the decision tree path

        """
        assert tree_idx >= 0 and tree_idx < len(self.decision_trees), \
            f"tree index {tree_idx} outside 0 and number of trees ({len(self.decision_trees)}) range"
        idx = self.get_int_idx(index)
        assert idx >= 0 and idx < len(self.X), \
            f"=index {idx} outside 0 and size of X ({len(self.X)}) range"
        
        if self.is_classifier:
            if pos_label is None: pos_label = self.pos_label
            return get_decisiontree_df(self.decision_trees[tree_idx], self.X.iloc[idx],
                    pos_label=pos_label)
        else:
            return get_decisiontree_df(self.decision_trees[tree_idx], self.X.iloc[idx])

    def decisiontree_df_summary(self, tree_idx, index, round=2, pos_label=None):
        """formats decisiontree_df in a slightly more human readable format.

        Args:
          tree_idx: the n'th tree in the random forest
          index: row index
          round:  (Default value = 2)
          pos_label:  positive class (Default value = None)

        Returns:
          dataframe with summary of the decision tree path

        """
        idx=self.get_int_idx(index)
        return decisiontree_df_summary(self.decisiontree_df(tree_idx, idx, pos_label=pos_label),
                    classifier=self.is_classifier, round=round)

    def decision_path_file(self, tree_idx, index):
        """get a dtreeviz visualization of a particular tree in the random forest.

        Args:
          tree_idx: the n'th tree in the random forest
          index: row index

        Returns:
          the path where the .svg file is stored.

        """
        if not self.graphviz_available:
            print("No graphviz 'dot' executable available!") 
            return None

        idx = self.get_int_idx(index)
        if self.is_regression:
            viz = dtreeviz(self.model.estimators_[tree_idx],
               self.X, self.y, 
               target_name='Target',
               #orientation ='LR',  # left-right orientation
               feature_names=self.columns,
               X=self.X.iloc[idx, :])
        elif self.is_classifier:
            viz = dtreeviz(self.model.estimators_[tree_idx],
               self.X, self.y, 
               target_name='Target',
               #orientation ='LR',  # left-right orientation
               feature_names=self.columns,
               class_names=self.labels,
               X=self.X.iloc[idx, :]) 
        return viz.save_svg()

    def decision_path(self, tree_idx, index):
        """get a dtreeviz visualization of a particular tree in the random forest.

        Args:
          tree_idx: the n'th tree in the random forest
          index: row index

        Returns:
          a IPython display SVG object for e.g. jupyter notebook.

        """
        if not self.graphviz_available:
            print("No graphviz 'dot' executable available!") 
            return None

        from IPython.display import SVG
        svg_file = self.decision_path_file(tree_idx, index)
        return SVG(open(svg_file,'rb').read())

    def decision_path_encoded(self, tree_idx, index):
        """get a dtreeviz visualization of a particular tree in the random forest.

        Args:
          tree_idx: the n'th tree in the random forest
          index: row index

        Returns:
          a base64 encoded image, for inclusion in websites (e.g. dashboard)
        

        """
        if not self.graphviz_available:
            print("No graphviz 'dot' executable available!")
            return None
        
        svg_file = self.decision_path_file(tree_idx, index)
        encoded = base64.b64encode(open(svg_file,'rb').read()) 
        #encoded = base64.b64encode(viz.svg()) 
        svg_encoded = 'data:image/svg+xml;base64,{}'.format(encoded.decode()) 
        return svg_encoded


    def plot_trees(self, index, highlight_tree=None, round=2, pos_label=None):
        """plot barchart predictions of each individual prediction tree

        Args:
          index: index to display predictions for
          highlight_tree:  tree to highlight in plot (Default value = None)
          round: rounding of numbers in plot (Default value = 2)
          pos_label: positive class (Default value = None)

        Returns:

        """
        #print('explainer call')
        idx=self.get_int_idx(index)
        assert idx is not None, 'invalid index'
        
        if self.is_classifier:
            if pos_label is None: pos_label = self.pos_label
            return plotly_tree_predictions(self.model, self.X.iloc[[idx]],
                        highlight_tree=highlight_tree, round=round, pos_label=self.pos_label)
        else:
            return plotly_tree_predictions(self.model, self.X.iloc[[idx]], 
                        highlight_tree=highlight_tree, round=round)

    def calculate_properties(self, include_interactions=True):
        """

        Args:
          include_interactions:  If False do not calculate shap interaction value
            (Default value = True)

        Returns:

        """
        _ = self.decision_trees
        super().calculate_properties(include_interactions=include_interactions)



class RandomForestClassifierExplainer(RandomForestExplainer, ClassifierExplainer):
    """RandomForestClassifierBunch inherits from both RandomForestExplainer and
    ClassifierExplainer.
    """


class RandomForestRegressionExplainer(RandomForestExplainer, RegressionExplainer):
    """RandomForestClassifierBunch inherits from both RandomForestExplainer and
    RegressionExplainer.
    """



class ClassifierBunch:
    """ """
    def __init__(self, *args, **kwargs):
        raise ValueError("ClassifierBunch has been deprecated, use ClassifierExplainer instead...")

class RegressionBunch:
    """ """
    def __init__(self, *args, **kwargs):
        raise ValueError("RegressionBunch has been deprecated, use RegressionrExplainer instead...")

class RandomForestExplainerBunch:
    """ """
    def __init__(self, *args, **kwargs):
        raise ValueError("RandomForestExplainerBunch has been deprecated, use RandomForestExplainer instead...")

class RandomForestClassifierBunch:
    """ """
    def __init__(self, *args, **kwargs):
        raise ValueError("RandomForestClassifierBunch has been deprecated, use RandomForestClassifierExplainer instead...")

class RandomForestRegressionBunch:
    """ """
    def __init__(self, *args, **kwargs):
        raise ValueError("RandomForestRegressionBunch has been deprecated, use RandomForestRegressionExplainer instead...")




