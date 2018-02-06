import numpy as np
import pandas as pd
from datetime import datetime

from bokeh.io import curdoc
from bokeh.plotting import figure, show
from bokeh.layouts import row, widgetbox
from bokeh.models import ColumnDataSource, DatetimeTickFormatter
from bokeh.palettes import brewer
from bokeh.models.widgets import Select, Div

#  Process the num-active csv so that it's in the right format to plot

df = pd.read_csv('/data_files/num-active.csv', parse_dates=(['period_end']))
df = (df.groupby(['period_end', 'country', 'membership_type'])['num_active']
        .sum()
        .unstack() # unstack the membership_type column
).reset_index()

top_markets = ['United Kingdom','United States', 'Australia', 'Canada', 'New Zealand']

df['country_cat'] = [x if x in top_markets else 'ROW' for x in df['country']] # Create a category for the countries and ROW

df.fillna(0, inplace=True) # replace NaN with 0

df['all_members'] = df.combined + df.homeowner + df.housesitter

# Set an inital state for plotting all member data
init = df.groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()

colors = brewer['Dark2'][3]

# Create the ColumnDataSource for plotting
growth_source = ColumnDataSource(data=dict(
    xs=[init.period_end,
        init.period_end,
        init.period_end],
    ys=[init.homeowner,
        init.housesitter,
        init.combined],
    colors=colors,
    labels=['Owners', 'Sitters', 'Combined']))

# Create figure for growth grapth
growth_p = figure(title="Membership Growth", plot_height=400, plot_width=400, x_axis_type='datetime')
growth_r = growth_p.multi_line(xs='xs', ys='ys', source=growth_source, color='colors', legend='labels')
growth_p.legend.location = "top_left"

# Create ratio ColumnDataSource for plotting
ratio_source = ColumnDataSource(data=dict(
    x=init.period_end,
    y=init.housesitter / init.homeowner))

# Create figure for ratio graph
ratio_p = figure(title="Membership Ratio", plot_height=400, plot_width=400, x_axis_type='datetime', y_range=(0,10))
ratio_r = ratio_p.line(x='x', y='y', source=ratio_source, color="#2222aa", line_width=1)

# Function to update plots
def update(attr, old, new):

    country = sel_country.value

    if country == 'All':
        data = df.groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    else:
        data = df[df.country_cat == country].groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    
    growth_source.data = dict(
        xs=[data.period_end, data.period_end, data.period_end],
        ys=[data.homeowner, data.housesitter, data.combined],
        colors=colors,
        labels=['Owners', 'Sitters', 'Combined'])

    ratio_source.data = dict(
        x=data.period_end,
        y=data.housesitter / data.homeowner)

    owner_count = (growth_source.data['ys'][0][last_count]).astype('str')
    sitter_count = (growth_source.data['ys'][1][last_count]).astype('str')
    combined_count = (growth_source.data['ys'][2][last_count]).astype('str')

    a_number.text = owner_count + " Owners, " + sitter_count + " Sitters,"  + combined_count + " Combined"

# Select box for country
country_options = ["All", "United Kingdom", "United States", "Australia", "Canada", "New Zealand", "ROW"]
sel_country = Select(title="Country:", options=country_options, value="All")
sel_country.on_change('value', update)

last_count = (growth_source.data['ys'][0].shape[0]) - 1
owner_count = (growth_source.data['ys'][0][last_count]).astype('str')
sitter_count = (growth_source.data['ys'][1][last_count]).astype('str')
combined_count = (growth_source.data['ys'][2][last_count]).astype('str')

a_number = Div(text=(owner_count + " Owners, " + sitter_count + " Sitters,"  + combined_count + " Combined"),
width=200, height=100)

# Set up layouts and add to document
inputs = widgetbox(sel_country, a_number)

curdoc().add_root(row(inputs, growth_p, ratio_p, width=1200))
curdoc().title = "Membership Growth & Ratio"