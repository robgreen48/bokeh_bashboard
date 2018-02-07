import numpy as np
import pandas as pd
import datetime

from bokeh.io import curdoc
from bokeh.plotting import figure, show
from bokeh.layouts import row, widgetbox, gridplot
from bokeh.models import ColumnDataSource, DatetimeTickFormatter, NumeralTickFormatter
from bokeh.palettes import brewer
from bokeh.models.widgets import Select, Div, Panel, Tabs

###
###
### Start growth data manipulation

member_numbers = pd.read_csv('data_files/num-active.csv', parse_dates=(['period_end']))
member_numbers = (member_numbers.groupby(['period_end', 'country', 'membership_type'])['num_active']
        .sum()
        .unstack() # unstack the membership_type column
).reset_index()

top_markets = ['United Kingdom','United States', 'Australia', 'Canada', 'New Zealand']

member_numbers['country_cat'] = [x if x in top_markets else 'ROW' for x in member_numbers['country']]
member_numbers.fillna(0, inplace=True)
member_numbers[['homeowner', 'housesitter', 'combined']] = member_numbers[['homeowner', 'housesitter', 'combined']].astype(int)

# Set an inital state for plotting all member data
all_members = member_numbers.groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()


# Create the ColumnDataSource for plotting
def create_growth_source(data):
    source = dict(
        xs=[data.period_end,
            data.period_end,
            data.period_end],
        ys=[data.homeowner,
            data.housesitter,
            data.combined],
        colors=brewer['Dark2'][3],
        labels=['Owners', 'Sitters', 'Combined'])

    return source

growth_source = ColumnDataSource(data=create_growth_source(all_members))


# Create figure for growth grapth
growth_p = figure(title="Membership Growth", plot_height=400, plot_width=400, x_axis_type='datetime')
growth_r = growth_p.multi_line(xs='xs', ys='ys', source=growth_source, color='colors', legend='labels')
growth_p.legend.location = "top_left"


# Create ratio ColumnDataSource for plotting
def create_ratio_source(data):
    source = dict(
        x=data.period_end,
        y=data.housesitter / data.homeowner)
    return source

ratio_source = ColumnDataSource(data=create_ratio_source(all_members))

# Create figure for ratio graph
ratio_p = figure(title="Membership Ratio", plot_height=400, plot_width=400, x_axis_type='datetime', y_range=(0,10))
ratio_r = ratio_p.line(x='x', y='y', source=ratio_source, color="#2222aa", line_width=1)


# Generate text for counts div
def generate_counts_html(source):

    last_count = (source.data['ys'][0].shape[0]) - 1
    owner_count = (source.data['ys'][0][last_count]).astype('str')
    sitter_count = (source.data['ys'][1][last_count]).astype('str')
    combined_count = (source.data['ys'][2][last_count]).astype('str')
    
    text = str("<ul><li>" + owner_count + " Owners</li>" + "<li>" + sitter_count + " Sitters </li>"  + "<li>" + combined_count + " Combined</li></ul>")
    
    return text


# Callback to update plots
def update(attr, old, new):

    country = sel_country.value

    if country == 'All':
        data = member_numbers.groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    else:
        data = member_numbers[member_numbers.country_cat == country].groupby('period_end')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    
    growth_source.data = create_growth_source(data)
    ratio_source.data = create_ratio_source(data)
    a_number.text = generate_counts_html(growth_source)


# Select box for country
country_options = ["All", "United Kingdom", "United States", "Australia", "Canada", "New Zealand", "ROW"]
sel_country = Select(title="Country:", options=country_options, value="All")
sel_country.on_change('value', update)

# Create div for totals
a_number = Div(text=generate_counts_html(growth_source), width=200, height=100)

# Set up layouts and add to tab1
growth_inputs = widgetbox(sel_country, a_number)
growth_layout = row(growth_inputs, growth_p, ratio_p, width=1200)
tab1 = Panel(child=growth_layout, title="Growth")

###
###
### Start Sitter success data manipulation

apps = pd.read_csv('data_files/180103-applications.csv', parse_dates=['date_created', 'last_modified'])
sitters = pd.read_csv('data_files/180103-sitters.csv', parse_dates=['fst_start_date', 'start_date', 'expires_date'])

apps = pd.merge(
    apps,
    sitters[['user_id','fst_start_date', 'billing_country']],
    left_on='suser_id',
    right_on='user_id',
    left_index=True)

apps['time_into_membership'] = apps.date_created - apps.fst_start_date
apps['is_assignment_filled'] = (apps.oconfirmed == 1) & (apps.sconfirmed ==1)

# Only look at applications from members in their first three months
relevant_applications = apps[(apps.time_into_membership <= datetime.timedelta(days=90)) & (apps.time_into_membership >= datetime.timedelta(days=0))]

REPORT_START = '01-Jan-2016'
REPORT_END = '31-Oct-2017'

num_of_apps = relevant_applications['suser_id'].value_counts() #Create series of the number of applications for every sitter
num_confirmed = relevant_applications.groupby('suser_id')['is_assignment_filled'].sum() #Create series of the number of confirmed applications for every sitter

onboarding_sitters = sitters[['user_id', 'fst_start_date', 'billing_country']].copy()
onboarding_sitters.set_index('user_id', inplace=True)

# Additional columns and indexing
onboarding_sitters['nb_applications'] = num_of_apps
onboarding_sitters['confirmed_sits'] = num_confirmed
onboarding_sitters['is_successful'] = onboarding_sitters.confirmed_sits > 0
onboarding_sitters.reset_index(inplace=True)
onboarding_sitters.set_index('fst_start_date', inplace=True)
onboarding_sitters = onboarding_sitters.fillna(0)
sampled_sitters = onboarding_sitters.loc[REPORT_START:REPORT_END].resample('M').agg({
    'nb_applications': np.sum,
    'confirmed_sits': np.mean,
    'is_successful': np.mean})

# Member activity data
num_sitters = onboarding_sitters.reset_index().groupby('fst_start_date')['user_id'].count()
num_inactive = onboarding_sitters[onboarding_sitters.nb_applications == 0].groupby('fst_start_date')['user_id'].count()
activity = pd.concat([num_sitters, num_inactive], axis=1)
activity.columns = ['num_sitters', 'num_inactive']
activity['percent_inactive'] = activity.num_inactive / activity.num_sitters
activity = activity.loc[REPORT_START:REPORT_END].resample('M').agg({
    'num_sitters': np.sum,
    'percent_inactive': np.mean})

sitter_onboarding_source = ColumnDataSource(data=dict(
    x=sampled_sitters.index,
    nb_applications=sampled_sitters.nb_applications,
    confirmed_sits=sampled_sitters.confirmed_sits,
    is_successful=sampled_sitters.is_successful))

# Create figure for sitter apps graph
sitter_apps_p = figure(title="New Sitter Applications", plot_height=400, plot_width=400, x_axis_type='datetime')
sitter_apps_r = sitter_apps_p.line(x='x', y='nb_applications', source=sitter_onboarding_source, color="#2222aa", line_width=1)

# Create figure for sitter confirmations graph
sitter_confirmed_p = figure(title="New Sitter Confirmations", plot_height=400, plot_width=400, x_axis_type='datetime')
sitter_confirmed_r = sitter_confirmed_p.line(x='x', y='confirmed_sits', source=sitter_onboarding_source, color="#2222aa", line_width=1)

# Create figure for sitter success graph
sitter_success_p = figure(title="New Sitter Success", plot_height=400, plot_width=400, x_axis_type='datetime')
sitter_success_r = sitter_success_p.line(x='x', y='is_successful', source=sitter_onboarding_source, color="#2222aa", line_width=1)
sitter_success_p.yaxis.formatter = NumeralTickFormatter(format="0%")

inactivity_source = ColumnDataSource(data=dict(
    x=activity.index,
    inactive=activity.percent_inactive,
    num_sitters=activity.num_sitters))

# Create figure for inactivity graph
sitter_inactivity_p = figure(title="New Sitter Inactivity Levels", plot_height=400, plot_width=400, x_axis_type='datetime')
sitter_inactivity_r = sitter_inactivity_p.line(x='x', y='inactive', source=inactivity_source, color="#2222aa", line_width=1)
sitter_inactivity_p.yaxis.formatter = NumeralTickFormatter(format="0%")

# Create figure for number of sitters graph
sitter_numbers_p = figure(title="New Sitter Numbers", plot_height=400, plot_width=400, x_axis_type='datetime')
sitter_numbers_r = sitter_numbers_p.line(x='x', y='num_sitters', source=inactivity_source, color="#2222aa", line_width=1)

sitter_onb_layout = gridplot([sitter_inactivity_p, sitter_apps_p, sitter_confirmed_p, sitter_numbers_p, sitter_success_p], ncols=3)
tab2 = Panel(child=sitter_onb_layout, title="Sitter Onboarding")
# additional tabs tab2, tab3....

# List of tabs
tabs = [tab1, tab2]

# Add tabs to curdoc
curdoc().add_root(Tabs(tabs=tabs))
curdoc().title = "Membership Growth & Ratio"