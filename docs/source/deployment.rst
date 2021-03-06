Deployment
**********

When deploying your dashboard it is better not to use the built-in flask
server but use more robust and scalable options like ``gunicorn`` and ``nginx``.

Deploying a single dashboard instance
=====================================

``Dash`` is built on top of ``Flask``, and so the dashbaord instance 
contains a Flask server. You can simply expose this server to host your dashboard.

The server can be found in ``ExplainerDashboard().app.server`` or with
the methods ``ExplainerDashboard.flask_server()``.

The code below is from `the deployed example to heroku <https://github.com/oegedijk/explainingtitanic/blob/master/dashboard.py>`_::

    from sklearn.ensemble import RandomForestClassifier

    from explainerdashboard.explainers import *
    from explainerdashboard.dashboards import *
    from explainerdashboard.datasets import *

    print('loading data...')
    X_train, y_train, X_test, y_test = titanic_survive()
    train_names, test_names = titanic_names()

    print('fitting model...')
    model = RandomForestClassifier(n_estimators=50, max_depth=5)
    model.fit(X_train, y_train)

    print('building Explainer...')
    explainer = RandomForestClassifierExplainer(model, X_test, y_test, 
                                cats=['Sex', 'Deck', 'Embarked'],
                                idxs=test_names, 
                                labels=['Not survived', 'Survived'])

    print('Building ExplainerDashboard...')
    db = ExplainerDashboard(explainer)

    server = db.app.server

If you name the file above ``dashboard.py``, then you can start the gunicorn
server with for example three workers and binding to port 8050 like this::

    gunicorn localhost:8050 dashboard:server


So here ``dashboard`` refers to ``dashboard.py`` and ``server`` refers to the ``server``
defined equal to ``db.app.server``.

If you want to have multiple workers to speed up your dashboard, you need
to preload the app before starting::

        gunicorn -w 3 --preload localhost:8050 dashboard:server



Deploying dashboard as part of Flask app on specific route
==========================================================

Another way to deploy the dashboard is to first start a ``Flask`` app, and then
use this app as the backend of the Dashboard, and host the dashboard on a specific
route. This way you can for example host multiple dashboard under different urls.
You need to pass the Flask ``server`` instance and the ``url_base_pathname`` to the
``ExplainerDashboard`` constructor, and then the dashboard itself can be found
under ``db.app.index``::

    from flask import Flask
    
    app = Flask(__name__)

    [...]
    
    db = ExplainerDashboard(explainer, server=app, url_base_pathname="/dashboard/")

    @app.route('/dashboard')
    def return_dashboard():
        return db.app.index()

Now you can start the dashboard by::

    gunicorn -w 3 --preload -b localhost:8050 dashboard:app

And you can visit the dashboard on ``http://localhost:8050/dashboard``.

Deploying as part of a multipage dash app
=========================================

**Under Construction**