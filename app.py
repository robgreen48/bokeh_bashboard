from flask import Flask, render_template, request

import numpy as np
import pandas as pd
import datetime
from time import strftime
from dateutil.relativedelta import relativedelta

from bokeh.io import curdoc
from bokeh.plotting import figure, show
from bokeh.layouts import row, column, widgetbox, gridplot
from bokeh.models import ColumnDataSource, DatetimeTickFormatter, NumeralTickFormatter, HoverTool
from bokeh.palettes import brewer
from bokeh.models.widgets import Select, Div, Panel, Tabs
from bokeh.embed import components

app = Flask(__name__)


def visualisation():
# prepare some data
    x = [1, 2, 3, 4, 5]
    y = [6, 7, 2, 4, 5]
    p = figure(title="simple line example", x_axis_label='x', y_axis_label='y')
    p.line(x, y, legend="Temp.", line_width=2)
    return p

# Index page, no args
@app.route('/')
def index():
    # TODO: render stuff
    plot = visualisation()
    script, div = components(plot)
    return render_template("index.html", script=script, div=div)

# With debug=True, Flask server will auto-reload 
# when there are code changes
if __name__ == '__main__':
	app.run(port=5000, debug=True)
