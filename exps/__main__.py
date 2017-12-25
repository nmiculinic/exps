# -*- coding: utf-8 -*-
import argparse
import datetime
import logging
from io import StringIO
from pprint import PrettyPrinter
from typing import List
from typing import NamedTuple

import dash
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
import sqlalchemy as sa
import voluptuous
import yaml
from dash.dependencies import Event
from dash.dependencies import Input
from dash.dependencies import Output
from dash.dependencies import State
from flask import redirect
from flask import Response
from fn import _
from functional import seq
from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy import Table

pp = PrettyPrinter()


class Question(NamedTuple):
    text: str


class Factor(NamedTuple):
    question_ids: List[int]
    name: str


schema = voluptuous.Schema({
    'questions': [lambda x: Question(text=x)],
    'factors':
    lambda x: [Factor(question_ids=seq(v).map(_ - 1).to_list(), name=k) for k, v in x.items()],
})


class Config(NamedTuple):
    questions: List[Question]
    factors: List[Factor]


def question_components(i: int, q: Question):
    return html.Div(
        html.Div(
            [
                html.H2(q.text, className='col-lg-12'),
                html.Div(
                    dcc.Slider(
                        min=1,
                        max=5,
                        step=1,
                        value=3,
                        id=f"q-{i}",
                        dots=True,
                    ),
                    className='col-lg-12'),
            ],
            className='row',
        ),
        className='col-md-3')


def output_slider(i: int, factor: Factor):
    return html.Div(
        html.Div(
            [
                html.H2(factor.name, className='col-lg-4'),
                html.Div(
                    dcc.Slider(
                        min=0,
                        max=1,
                        step=0.01,
                        value=0.5,
                        disabled=True,
                        id=f"f-{i}",
                    ),
                    className='col-lg-8'),
            ],
            className='row',
        ),
        className='col-lg-12')


def link_factor(app: dash.Dash, i: int, factor: Factor):
    @app.callback(
        Output(f"f-{i}", 'value'),
        inputs=[Input(f"q-{x}", 'value') for x in factor.question_ids])
    def f(*args):
        sol = seq(args).map(_ - 1).sum() / (len(args) * 4)
        logging.getLogger('calc_factor').info(
            f"{pp.pformat({'args': args, 'factor': factor._asdict(), 'sol': sol})}"
        )
        return sol


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=voluptuous.IsFile(), required=True)
    parser.add_argument(
        '--db',
        default='sqlite:///:memory',
        help='db engine connection string')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        cfg = Config(**schema(yaml.load(f)))
    logging.info(f"{pp.pformat(cfg)}")

    engine = create_engine(args.db)
    metadata = MetaData()
    responses = Table('responses', metadata,
                      Column('time', sa.DateTime),
                      *[Column(q.text, sa.Float) for q in cfg.questions])
    metadata.create_all(engine)

    app = dash.Dash(url_base_pathname='/app')
    components = [
        question_components(i, x) for i, x in enumerate(cfg.questions)
    ]

    results = [
        html.Button("Submit!", id='submit', className='col-lg-12'),
        *[output_slider(i, f) for i, f in enumerate(cfg.factors)],
        html.A("Download CSV data", href='download_csv')
    ]
    app.layout = html.Div(
        [
            html.Div(
                [
                    html.Div(components, className='col-lg-6'),
                    html.Div(results, className='col-lg-6'),
                ],
                className='row'),
            html.Div(
                [
                    html.Div("", id="saved_callback"),
                ],
                style={
                    'display': 'none'
                })
        ],
        className='container-fluid',
    )

    for i, f in enumerate(cfg.factors):
        link_factor(app, i, f)

    @app.callback(
        Output('saved_callback', 'children'),
        state=[State(f'q-{i}', 'value') for i in range(len(cfg.questions))],
        events=[Event('submit', 'click')],
    )
    def dump_to_db(*args):
        with engine.connect() as conn:
            conn.execute(responses.insert().values({
                'time': datetime.datetime.utcnow(),
                **{
                    q.text: float(r) for q, r in zip(cfg.questions, args)
                }
            }))
        return "whatever"

    @app.server.route('/')
    def red():
        return redirect('/app')

    @app.server.route('/download_csv', methods=['GET'])
    def download_csv():
        s = StringIO()
        with engine.connect() as conn:
            data = pd.read_sql_query(
                sql=sa.text(f"SELECT * FROM {responses.name}"), con=conn)
        data.to_csv(s)
        return Response(
            s.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-disposition": f"attachment; filename=data.csv"
            })

    # app.css.config.serve_locally = True
    app.scripts.config.serve_locally = True

    app.css.append_css({
        "external_url":
        "https://codepen.io/chriddyp/pen/bWLwgP.css"
    })
    app.css.append_css({
        "external_url":
        "https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta/css/bootstrap.min.css"
    })

    app.run_server(debug=True)
