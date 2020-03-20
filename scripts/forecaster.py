
import numpy as np
import pandas as pd
from scipy.stats import boxcox
from scipy.special import inv_boxcox
from fbprophet import Prophet
pd.plotting.register_matplotlib_converters()
import pmdarima as pm
from utils import ProgressBar

class ProphetForecaster:
    def __init__(
        self, 
        use_boxcox=True,
        yearly_seasonality="auto",
        weekly_seasonality=False,
        daily_seasonality=False,
        confidence_interval=0.8,
        **kwargs):
        
        self.models = dict()
        self.fcst = dict()
        self.lmbda_boxcox = dict()
        self.use_boxcox = use_boxcox
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.daily_seasonality = daily_seasonality
        self.prophet_config = kwargs

    def fit(self, train_df):
        print("Fitting...")
        progress_bar = ProgressBar(len(train_df.columns))
        
        for item in train_df.columns:
            target = train_df[item].dropna()
            if self.use_boxcox:
                idx = target.index
                target, self.lmbda_boxcox[item] = boxcox(target)
                target = pd.Series(target, index=idx)
            target.index.name = "ds"
            target.name = "y"
            target = target.reset_index()
            self.models[item] = Prophet(
                yearly_seasonality=self.yearly_seasonality,
                weekly_seasonality=self.weekly_seasonality,
                daily_seasonality=self.daily_seasonality,
                **self.prophet_config)
            self.models[item].fit(target)
            progress_bar.update()
        progress_bar.finish()
        return self.models
            
    def predict(self, steps, freq="D"):
        print("Forecasting...")
        progress_bar = ProgressBar(len(self.models.items()))
        for item, model in self.models.items():
            future = model.make_future_dataframe(steps, freq=freq)
            pred = model.predict(future).set_index("ds")
            pred = pred[["yhat", "yhat_lower", "yhat_upper"]]
            self.fcst[item] = pred
            if self.use_boxcox:
                self.fcst[item] = inv_boxcox(
                    self.fcst[item], 
                    self.lmbda_boxcox[item])
            progress_bar.update()
        progress_bar.finish()
        fcst_df = pd.concat(self.fcst, axis=1).sort_index(axis=1)
        return fcst_df

class ARIMAForecaster:
    def __init__(
        self,
        use_boxcox=True,
        n_fourier_terms=10,
        seasonality=[365.25],
        confidence_interval=0.8,
        **kwargs):
    
        self.models = dict()
        self.fcst = dict()
        self.lmbda_boxcox = dict()
        self.use_boxcox = use_boxcox
        self.n_fourier_terms = n_fourier_terms
        self.seasonality = seasonality
        self.confidence_interval = confidence_interval
        self.arima_config = kwargs

    def fit(self, train_df):
        self.train_ds = train_df.index
        print("Fitting...")
        progress_bar = ProgressBar(len(train_df.columns))
        for item in train_df.columns:
            target = train_df[item].interpolate().bfill()
            if self.use_boxcox:
                idx = target.index
                target, self.lmbda_boxcox[item] = boxcox(target)
                target = pd.Series(target, index=idx)
            self.models[item] = pm.auto_arima(
                target,
                seasonal=False,
                exogenous=fourier(
                    len(target), 
                    seasonality=self.seasonality, 
                    n_terms=self.n_fourier_terms), 
                method="bfgs",
                suppress_warnings=True,
                **self.arima_config)
            progress_bar.update()
        progress_bar.finish()
        return self.models
            
    def predict(self, steps):
        print("Forecasting...")
        progress_bar = ProgressBar(len(self.models.items()))
        self.fcst_ds = pd.date_range(
            start=self.train_ds.min(), 
            freq="D", 
            periods=len(self.train_ds)+steps)[-365:]
        for item, model in self.models.items():
            pred = model.predict(
                exogenous=fourier(
                    steps, 
                    seasonality=self.seasonality, 
                    n_terms=self.n_fourier_terms),
                n_periods=steps, 
                return_conf_int=True,
                alpha=(1.0 - self.confidence_interval))
            self.fcst[item] = pd.DataFrame(
                {"yhat":pred[0],
                 "yhat_lower":pred[1][:,0],
                 "yhat_upper":pred[1][:,1]},
                index=self.fcst_ds)
            if self.use_boxcox:
                self.fcst[item] = inv_boxcox(
                    self.fcst[item], 
                    self.lmbda_boxcox[item])
            progress_bar.update()
        progress_bar.finish()
        return pd.concat(self.fcst, axis=1)
    
def fourier(steps, seasonality, n_terms=10):
    coeff_list = []
    t = np.arange(0, steps)
    for period in seasonality:
        coeff_M = np.zeros((steps, 2*n_terms))
        for k in range(n_terms):
            coeff_M[:, 2*k] = np.sin(2*np.pi*(k+1)*t/period)
            coeff_M[:, 2*k+1] = np.cos(2*np.pi*(k+1)*t/period)
        coeff_list.append(coeff_M)
    coeff = np.concatenate(coeff_list, axis=1)
    return coeff
