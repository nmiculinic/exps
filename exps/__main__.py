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


class Factor:
    question_ids: List[int]
    name: str
    rev: List[bool]

    def __init__(self, fct, name):
        if ',' in fct:
            fct = [x.strip() for x in fct.split(',')]
        self.name = name
        self.question_ids = []
        self.rev = []
        for fact in fct:
            if 'R' == fact[-1]:
                self.rev.append(True)
                self.question_ids.append(int(fact[:-1]) - 1)
            else:
                self.rev.append(False)
                self.question_ids.append(int(fact) - 1)

    def _asdict(self):
        return dict(vars(self))


schema = voluptuous.Schema({
    'questions': [lambda x: Question(text=x)],
    'factors':
    lambda x: [Factor(v, name=k) for k, v in x.items()],
})


class Config(NamedTuple):
    questions: List[Question]
    factors: List[Factor]


def question_components(i: int, q: Question):
    return html.Div(
        html.Div(
            [
                html.H2(q.text, className='col-md-6'),
                html.Div(
                    dcc.Slider(
                        min=1,
                        max=5,
                        step=1,
                        value=3,
                        id=f"q-{i}",
                        dots=True,
                    ),
                    className='col-md-6'),
            ],
            className='row',
        ),
        className='col-lg-12')


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
    def apply_reverse(tt):
        a, r = tt
        return 4 - a if r else a

    @app.callback(
        Output(f"f-{i}", 'value'),
        inputs=[Input(f"q-{x}", 'value') for x in factor.question_ids],
        events=[Event('submit', 'click')],
    )
    def f(*args):
        sol = seq(args).map(_ - 1).zip(factor.rev).map(apply_reverse).sum() / (
            len(args) * 4)
        logging.getLogger('calc_factor').info(
            f"{pp.pformat({'args': args, 'factor': factor._asdict(), 'sol': sol})}"
        )
        return sol


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=voluptuous.IsFile(), required=True)
    parser.add_argument('--port', type=int, default=8050)
    parser.add_argument(
        '--db',
        default='sqlite://',
        help=
        'db engine connection string.\nSee http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls for more details.'
    )
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        cfg = Config(**schema(yaml.load(f)))
    logging.info(f"{pp.pformat(cfg)}")

    engine = create_engine(args.db)
    metadata = MetaData()
    responses = Table('responses', metadata,
                      Column('time', sa.DateTime),
                      *[Column(q.text, sa.Float) for q in cfg.questions])
    print(metadata.create_all(engine))

    app = dash.Dash(url_base_pathname='/app')
    components = html.Div(
        [question_components(i, x) for i, x in enumerate(cfg.questions)],
        className='row')

    results = html.Div(
        [
            html.Button("Submit!", id='submit', className='col-lg-12'),
            *[output_slider(i, f) for i, f in enumerate(cfg.factors)],
            html.A(
                "Download CSV data",
                href='download_csv',
                className='col-lg-12')
        ],
        className='row')
    app.layout = html.Div(
        [
            html.Div(
                [
                    html.Div(
                        html.H2("""
Here are a number of characteristics that may or may not apply to you. For example, do you agree
that you are someone who likes to spend time with others? Please write a number next to each
statement to indicate the extent to which you agree or disagree with that statement. Leftmost (number 1) is strongly disagree, rightmost (number 5) is strongly agree.
                    """),
                        className='col-lg-12'),
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

    app.run_server(port=args.port)


if __name__ == "__main__":
    main()
