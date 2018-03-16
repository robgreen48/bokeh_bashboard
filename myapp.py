from flask import Flask, render_template, request
from flask_httpauth import HTTPBasicAuth

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

import settings

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {
    settings.GLOBALUSER: settings.GLOBALPASS
}

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None


TOOLS = "pan,wheel_zoom,box_zoom,reset"

REPORT_START = '01-Jan-2016' # Earliest point for all plots
REPORT_END = '30-Nov-2017' # End point for onboarding reports, usually 3 months in the past


### Start growth data manipulation ###

member_numbers = pd.read_csv('data_files/180301-num-active.csv', parse_dates=(['period']))
member_numbers = (member_numbers.groupby(['period', 'country', 'membership_type'])['num_active']
        .sum()
        .unstack() # unstack the membership_type column
).reset_index()

top_markets = ['United Kingdom','United States', 'Australia', 'Canada', 'New Zealand']

member_numbers['country_cat'] = [x if x in top_markets else 'ROW' for x in member_numbers['country']]
member_numbers.fillna(0, inplace=True)
member_numbers[['homeowner', 'housesitter', 'combined']] = member_numbers[['homeowner', 'housesitter', 'combined']].astype(int)

# Set an inital state for plotting all member data
all_members = member_numbers.groupby('period')[['homeowner', 'housesitter', 'combined']].sum().reset_index()


# Create the ColumnDataSource for plotting
def create_growth_source(data):
    source = dict(
        x=data.period,
        Owners=data.homeowner,
        Sitters=data.housesitter,
        Combined=data.combined,
        datestr=[d.strftime("%d-%m-%Y") for d in data.period])

    return source

growth_source = ColumnDataSource(data=create_growth_source(all_members))

growth_p = figure(title="Membership Growth", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Members", tools=TOOLS)

for idx, member in enumerate(['Owners', 'Sitters', 'Combined']):
    g1 = growth_p.line(x='x', y=member, source=growth_source, legend="Membership = {}".format(member), color=brewer['Dark2'][3][idx], line_width=2)

growth_p.add_tools(HoverTool(renderers=[g1], show_arrow=False, line_policy='next', tooltips=[
        ('Owners', '@Owners'),
        ('Sitters', '@Sitters'),
        ('Combined', '@Combined'),
        ('Date',  '@datestr')],
    mode='vline'
    )
)

growth_p.legend.location = "top_left"


# Create ratio ColumnDataSource for plotting
def create_ratio_source(data):
    source = dict(
        x=data.period,
        y=data.housesitter / data.homeowner,
        datestr=[d.strftime("%d-%m-%Y") for d in data.period])
    return source

ratio_source = ColumnDataSource(data=create_ratio_source(all_members))

ratio_p = figure(title="Membership Ratio (Sitters:Owners)", plot_height=300, plot_width=1000, x_axis_type='datetime', y_range=(0,12), y_axis_label="Ratio", tools=TOOLS)
ratio_p.square(x='x', y='y', source=ratio_source, color="#2222aa", fill_color=None, line_width=1)
ratio_p.line(x='x', y='y', source=ratio_source, color="#2222aa", line_width=1)
ratio_p.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Ratio', '@y'),
        ('Date',  '@datestr'),]
    , mode='vline')
)

# Generate text for counts div
def generate_counts_html(source):

    last_count = (source.data['Owners'].shape[0]) - 1
    owner_count = (source.data['Owners'][last_count]).astype('str')
    sitter_count = (source.data['Sitters'][last_count]).astype('str')
    combined_count = (source.data['Combined'][last_count]).astype('str')
    
    text = str("<ul><li>" + owner_count + " Owners</li>" + "<li>" + sitter_count + " Sitters </li>"  + "<li>" + combined_count + " Combined</li></ul>")
    
    return text


# Callback to update plots
def update(attr, old, new):

    country = sel_country.value

    if country == 'All':
        data = member_numbers.groupby('period')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    else:
        data = member_numbers[member_numbers.country_cat == country].groupby('period')[['homeowner', 'housesitter', 'combined']].sum().reset_index()
    
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
growth_inputs = row(sel_country, a_number)
growth_layout = column(growth_inputs, growth_p, ratio_p, width=1200)
tab1 = Panel(child=growth_layout, title="Membership Growth")


### Start Sitter success data manipulation ###

apps = pd.read_csv('data_files/180301-applications.csv', parse_dates=['date_created', 'last_modified'])
sitters = pd.read_csv('data_files/180301-sitters.csv', parse_dates=['fst_start_date', 'start_date', 'expires_date'])

apps = pd.merge(
    apps,
    sitters[['user_id','fst_start_date', 'billing_country']],
    left_on='suser_id',
    right_on='user_id',
    left_index=True)

apps['time_into_membership'] = apps.date_created - apps.fst_start_date
apps['is_assignment_filled'] = (apps.oconfirmed == 1) & (apps.sconfirmed ==1)

# Only look at applications from members in their first three months
relevant_applications = apps[
    (apps.time_into_membership <= datetime.timedelta(days=90))
    & (apps.time_into_membership >= datetime.timedelta(days=0))
]

num_of_apps = relevant_applications['suser_id'].value_counts() #Create series of the number of applications for every sitter
num_confirmed = relevant_applications.groupby('suser_id')['is_assignment_filled'].sum() #Create series of the number of confirmed applications for every sitter

onboarding_sitters = sitters[['user_id', 'fst_start_date', 'billing_country']].copy()
onboarding_sitters.set_index('user_id', inplace=True)

# Additional columns and indexing
onboarding_sitters['nb_applications'] = num_of_apps
onboarding_sitters['confirmed_sits'] = num_confirmed
onboarding_sitters['is_successful'] = onboarding_sitters.confirmed_sits > 0
onboarding_sitters['country_cat'] = [x if x in top_markets else 'ROW' for x in onboarding_sitters['billing_country']]
onboarding_sitters.reset_index(inplace=True)
onboarding_sitters.set_index('fst_start_date', inplace=True)
onboarding_sitters = onboarding_sitters.fillna(0)


def create_sitter_onboarding_source(data):

    sampled_sitters = data.loc[REPORT_START:REPORT_END].resample('M').agg({
        'nb_applications': np.sum,
        'confirmed_sits': np.mean,
        'is_successful': np.mean
        }
    )

    num_sitters = data.reset_index().groupby('fst_start_date')['user_id'].count()
    num_inactive = data[data.nb_applications == 0].groupby('fst_start_date')['user_id'].count()
    activity = pd.concat([num_sitters, num_inactive], axis=1)
    activity.columns = ['num_sitters', 'num_inactive']
    activity['percent_inactive'] = activity.num_inactive / activity.num_sitters

    sampled_activity = activity.loc[REPORT_START:REPORT_END].resample('M').agg({
    'num_sitters': np.sum,
    'percent_inactive': np.mean})

    source = dict(
        x=sampled_sitters.index,
        nb_applications=sampled_sitters.nb_applications,
        confirmed_sits=sampled_sitters.confirmed_sits,
        is_successful=sampled_sitters.is_successful,
        percent_inactive=sampled_activity.percent_inactive,
        num_sitters=sampled_activity.num_sitters,
        datestr=[d.strftime("%d-%m-%Y") for d in sampled_sitters.index])

    return source

sitter_onboarding_source = ColumnDataSource(data=create_sitter_onboarding_source(onboarding_sitters))


# Callback to update sitter onboarding plots
def update_sitter_onboarding(attr, old, new):

    country = sel_country2.value

    if country == 'All':
        so_data = onboarding_sitters
    else:
        so_data = onboarding_sitters[onboarding_sitters.country_cat == country]
    
    # Update the source data
    sitter_onboarding_source.data = create_sitter_onboarding_source(so_data)

so_plots_title_map = {
    'nb_applications': 'New Sitter Applications',
    'confirmed_sits': 'Confirmed Sits',
    'percent_inactive': 'New Sitter Inactivity',
    'num_sitters': 'Number Of New Sitters'}

p_so_success = figure(title="New Sitter Success", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Percent Successful", tools=TOOLS)
p_so_success.square(x='x', y='is_successful', source=sitter_onboarding_source, color="#2222aa", fill_color=None, line_width=1)
p_so_success.line(x='x', y='is_successful', source=sitter_onboarding_source, color="#2222aa", line_width=1)
p_so_success.yaxis.formatter = NumeralTickFormatter(format="0%")
p_so_success.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Success Rate', '@is_successful{0.00%}'),
        ('Date',  '@datestr'),]
    , mode='vline')
)
so_plots = []

# Plot all ColumnDataSource values
for c, col in enumerate(['nb_applications', 'confirmed_sits', 'percent_inactive', 'num_sitters']):
    fig = figure(title=so_plots_title_map[col], plot_height=250, plot_width=500, x_axis_type='datetime', tools=TOOLS)
    fig.line(x='x', y=col, source=sitter_onboarding_source, color=brewer['Dark2'][5][c], line_width=1)
    so_plots.append(fig)

so_plots[2].yaxis.formatter = NumeralTickFormatter(format="0%")

sel_country2 = Select(title="Country:", options=country_options, value="All")
sel_country2.on_change('value', update_sitter_onboarding)

so_inputs = widgetbox(sel_country2)

# sitter_onb_layout = gridplot([so_inputs, sitter_inactivity_p, sitter_apps_p, sitter_confirmed_p, sitter_numbers_p, sitter_success_p], ncols=3)
sitter_onb_layout = column(so_inputs, p_so_success, gridplot(so_plots, ncols=2))
tab2 = Panel(child=sitter_onb_layout, title="Sitter Onboarding")
# additional tabs tab2, tab3....


### Start Owner success data manipulation ###

asgnmts = pd.read_csv('data_files/180301-assignments.csv', parse_dates=['created_date', 'start_date', 'end_date'])
asgnmts['is_assignment_filled'] = asgnmts.sid.notnull()

app_count = apps.groupby('assignment_id')['req_type'].count()
asgnmts.set_index('aid', inplace=True)
asgnmts['nb_applications'] = app_count

owners = pd.read_csv('data_files/180301-owners.csv', parse_dates=['joined_date', 'fst_start_date', 'start_date', 'expires_date', 'published_date'])
assignments_impr = pd.merge(asgnmts,
                            owners[['user_id','billing_country', 'fst_start_date']],
                            left_on='ouser_id', right_on='user_id')
assignments_impr['time_into_membership'] = assignments_impr.created_date - assignments_impr.fst_start_date

# select only assignments that were posted in first three months of membership
relevant_assignments = (
    assignments_impr[(assignments_impr.time_into_membership <= datetime.timedelta(days=90)) 
                     & (assignments_impr.time_into_membership >= datetime.timedelta(days=0))]
).copy()
relevant_assignments['country_cat'] = [x if x in top_markets else 'ROW' for x in relevant_assignments['billing_country']]


num_of_assignments = relevant_assignments['user_id'].value_counts()
num_confirmed_sitters = relevant_assignments.groupby('user_id')['is_assignment_filled'].sum()
num_apps = relevant_assignments.groupby('user_id')['nb_applications'].sum()

owners.set_index('user_id', inplace=True)
owners['nb_assignments'] = num_of_assignments
owners['nb_confirmed_sitters'] = num_confirmed_sitters
owners['nb_applications'] = num_apps
owners['is_successful'] = owners.nb_confirmed_sitters > 0
owners['nb_apps_per_assignment'] = owners.nb_applications / owners.nb_assignments
owners['country_cat'] = [x if x in top_markets else 'ROW' for x in owners['billing_country']]
owners = owners.fillna(0)
owners.reset_index(inplace=True)
owners.set_index('fst_start_date', inplace=True)


def create_owner_onboarding_source(owner_data, assignment_data):

    sampled_owners = owner_data.loc[REPORT_START:REPORT_END].resample('M').agg({
        'nb_assignments': np.sum,
        'is_successful': np.mean
        }
    )
    sampled_active_owners = owner_data[owner_data.nb_assignments > 0].loc[REPORT_START:REPORT_END].resample('M').mean()

    num_owners = owner_data.groupby('fst_start_date')['user_id'].count()
    num_owners_inactive = owner_data[owner_data.nb_assignments == 0].groupby('fst_start_date')['user_id'].count()
    owner_activity = pd.concat([num_owners, num_owners_inactive], axis=1)
    owner_activity.columns = ['num_owners', 'num_inactive']
    owner_activity['percent_inactive'] = owner_activity.num_inactive / owner_activity.num_owners

    sampled_activity = owner_activity.loc[REPORT_START:REPORT_END].resample('M').agg({
        'num_owners': np.sum,
        'percent_inactive': np.mean
        }
    )
    sampled_assignments = assignment_data.set_index('fst_start_date').loc[REPORT_START:REPORT_END].resample('M').mean()

    source = dict(
        x=sampled_owners.index,
        nb_assignments=sampled_owners.nb_assignments,
        nb_apps_per_assignment=sampled_active_owners.nb_apps_per_assignment,
        is_successful=sampled_owners.is_successful,
        percent_inactive=sampled_activity.percent_inactive,
        nb_owners=sampled_activity.num_owners,
        confirmation_rate=sampled_assignments.is_assignment_filled,
        datestr=[d.strftime("%d-%m-%Y") for d in sampled_owners.index])

    return source

owner_onboarding_source = ColumnDataSource(data=create_owner_onboarding_source(owners, relevant_assignments))

# Callback to update sitter onboarding plots
def update_owner_onboarding(attr, old, new):

    country = sel_country3.value

    if country == 'All':
        oo_owner_data = owners
        oo_assignment_data = relevant_assignments
    else:
        oo_owner_data = owners[owners.country_cat == country]
        oo_assignment_data = relevant_assignments[relevant_assignments.country_cat == country]
    
    # Update the source data
    owner_onboarding_source.data = create_owner_onboarding_source(oo_owner_data, oo_assignment_data)

oo_plots_title_map = {
    'nb_assignments': 'New Owner Assignments',
    'percent_inactive': 'New Owner Inactivity',
    'nb_owners': 'Number Of New Owners',
    'confirmation_rate': 'New Owner Confirmation Rate'}

p_oo_success = figure(title="New Owner Success", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Percent Successful", tools=TOOLS)
p_oo_success.square(x='x', y='is_successful', source=owner_onboarding_source, color="#2222aa", fill_color=None, line_width=1)
p_oo_success.line(x='x', y='is_successful', source=owner_onboarding_source, color="#2222aa", line_width=1)
p_oo_success.yaxis.formatter = NumeralTickFormatter(format="0%")
p_oo_success.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Success Rate', '@is_successful{0.00%}'),
        ('Date',  '@datestr'),]
    , mode='vline')
)

oo_plots = []

# Plot all ColumnDataSource values
for c, col in enumerate(['nb_assignments', 'percent_inactive', 'nb_owners', 'confirmation_rate']):
    fig = figure(title=oo_plots_title_map[col], plot_height=250, plot_width=500, x_axis_type='datetime', tools=TOOLS)
    fig.line(x='x', y=col, source=owner_onboarding_source, color=brewer['Dark2'][6][c], line_width=1)
    oo_plots.append(fig)

oo_plots[1].yaxis.formatter = NumeralTickFormatter(format="0%")
oo_plots[3].yaxis.formatter = NumeralTickFormatter(format="0%")

sel_country3 = Select(title="Country:", options=country_options, value="All")
sel_country3.on_change('value', update_owner_onboarding)

oo_inputs = widgetbox(sel_country3)

oo_layout = column(oo_inputs, p_oo_success, gridplot(oo_plots, ncols=2))
tab3 = Panel(child=oo_layout, title="Owner Onboarding")


### Start Network Health data manipulation ###

# Create dfs from original uploads
asgnmts.reset_index(inplace=True, drop=False)
nh_assignments = asgnmts.copy()

nh_applications = (
    pd.merge(apps, nh_assignments[['aid', 'created_date']],
             how='left',
             left_on='assignment_id',
             right_on='aid')
)

nh_applications = nh_applications[~nh_applications.aid.isnull()]
nh_applications.set_index('created_date', drop=False, inplace=True)
nh_assignments.set_index('created_date', drop=False, inplace=True)

def calculate_rolling(apps_data, assgs_data, date_index):
    
    values = {'owners':[],
              'successful_owners' :[],
              'applications' :[],
              'assignments':[],
              'filled_assignments':[],
              'sitters':[],
              'successful_sitters':[]
        }

    for day in date_index:
        twelve_months_prior = day - relativedelta(months=12)

        app_view = apps_data.loc[str(twelve_months_prior):str(day.date())] # slice of applications df
        assg_view = assgs_data.loc[str(twelve_months_prior):str(day.date())] # slice of assignments df

        values['owners'].append(assg_view.ouser_id.nunique())
        values['sitters'].append(app_view.suser_id.nunique())
        values['applications'].append(app_view.request_id.count())
        values['assignments'].append(assg_view.aid.nunique())
        values['filled_assignments'].append(assg_view.is_assignment_filled.sum())
        values['successful_sitters'].append(assg_view[assg_view.is_assignment_filled ==1].suser_id.nunique())
        values['successful_owners'].append(assg_view[assg_view.is_assignment_filled ==1].ouser_id.nunique())

    return pd.DataFrame(data=values, index=date_index)


nh_index = pd.date_range(start=REPORT_START, end=nh_applications.created_date.max()) # create index of dates

# create df from values dictionary
rolling_data = calculate_rolling(nh_applications, nh_assignments, nh_index)

# broadcast new calculated columns
rolling_data['assignments_per_owner'] = rolling_data.assignments / rolling_data.owners
rolling_data['apps_per_assignment'] = rolling_data.applications / rolling_data.assignments
rolling_data['owner_success'] = rolling_data.successful_owners / rolling_data.owners
rolling_data['confirmation_rate'] = rolling_data.filled_assignments / rolling_data.assignments
rolling_data['sits_per_sitter'] = (rolling_data.filled_assignments / rolling_data.sitters)
rolling_data['sitter_success'] = rolling_data.successful_sitters / rolling_data.sitters
rolling_data['member_ratio'] = rolling_data.sitters / rolling_data.owners

def create_rolling_data_source(data):
    source = dict(
        x=data.index,
        assignments_per_owner=data.assignments_per_owner,
        apps_per_assignment=data.apps_per_assignment,
        owner_success=data.owner_success,
        confirmation_rate=data.confirmation_rate,
        sits_per_sitter=data.sits_per_sitter,
        sitter_success=data.sitter_success,
        member_ratio=data.member_ratio,
        datestr=[d.strftime("%d-%m-%Y") for d in data.index])

    return source

rolling_data_source = ColumnDataSource(data=create_rolling_data_source(rolling_data))

# Create figure for sitter success
# active_sitter_success_p = figure(title="Active Sitter Success", plot_height=400, plot_width=400, x_axis_type='datetime', tools=TOOLS)
# active_sitter_success_p.line(x='x', y='sitter_success', source=rolling_data_source)

active_sitter_success_p = figure(title="Active Sitter Success", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Percent Successful", tools=TOOLS)
active_sitter_success_p.line(x='x', y='sitter_success', source=rolling_data_source, color=brewer['Dark2'][7][4], line_width=2)
active_sitter_success_p.yaxis.formatter = NumeralTickFormatter(format="0%")
active_sitter_success_p.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Success Rate', '@sitter_success{0.00%}'),
        ('Date',  '@datestr'),]
    , mode='vline')
)

active_owner_success_p = figure(title="Active Owner Success", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Percent Successful", tools=TOOLS)
active_owner_success_p.line(x='x', y='owner_success', source=rolling_data_source, color=brewer['Dark2'][7][5], line_width=2)
active_owner_success_p.yaxis.formatter = NumeralTickFormatter(format="0%")
active_owner_success_p.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Success Rate', '@owner_success{0.00%}'),
        ('Date',  '@datestr'),]
    , mode='vline')
)

nh_plots_title_map = {
    'assignments_per_owner': 'Assignments Per Owner',
    'apps_per_assignment': 'Number Of Applications Per Assignment',
    'confirmation_rate': 'Confirmation Rate',
    'sits_per_sitter': 'Sits Per Sitter'}

nh_plots = []

# Plot all ColumnDataSource values
for c, col in enumerate(['assignments_per_owner', 'apps_per_assignment', 'confirmation_rate', 'sits_per_sitter']):
    fig = figure(title=nh_plots_title_map[col], plot_height=250, plot_width=500, x_axis_type='datetime', tools=TOOLS)
    fig.line(x='x', y=col, source=rolling_data_source, color=brewer['Dark2'][7][c], line_width=1)
    nh_plots.append(fig)

nh_plots[2].yaxis.formatter = NumeralTickFormatter(format="0%")

active_member_ratio_p = figure(title="Active Member Ratio", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Ratio", tools=TOOLS)
active_member_ratio_p.line(x='x', y='member_ratio', source=rolling_data_source, color=brewer['Dark2'][7][6], line_width=2)
active_member_ratio_p.add_tools(HoverTool(line_policy='next', tooltips=[
        ('Ratio', '@member_ratio'),
        ('Date',  '@datestr'),]
    , mode='vline')
)

nh_layout = column(active_sitter_success_p, active_owner_success_p, gridplot(nh_plots, ncols=2), active_member_ratio_p)

tab4 = Panel(child=nh_layout, title="Network Health")

# Layout of tabs for the whole dashboard
tabs = [tab1, tab2, tab3, tab4]

# Add tabs to curdoc
# curdoc().add_root(Tabs(tabs=tabs))
# curdoc().title = "Membership Growth & Ratio"

# Index page, no args
@app.route('/')
@auth.login_required
def index():
    # TODO: render stuff
    script, div = components(Tabs(tabs=tabs))
    return render_template("index.html", script=script, div=div)

# With debug=True, Flask server will auto-reload 
# when there are code changes
if __name__ == '__main__':
    app.run(port=5000, debug=True)