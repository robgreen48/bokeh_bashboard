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

apps = pd.read_csv('data_files/180201-applications.csv', parse_dates=['date_created', 'last_modified'])
sitters = pd.read_csv('data_files/180201-sitters.csv', parse_dates=['fst_start_date', 'start_date', 'expires_date'])

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
        inactive=sampled_activity.percent_inactive,
        num_sitters=sampled_activity.num_sitters)

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


# Create figure for sitter apps graph
sitter_apps_p = figure(title="New Sitter Applications", plot_height=300, plot_width=400, x_axis_type='datetime')
sitter_apps_r = sitter_apps_p.line(x='x', y='nb_applications', source=sitter_onboarding_source, color="#2222aa", line_width=1)

# Create figure for sitter confirmations graph
sitter_confirmed_p = figure(title="New Sitter Confirmations", plot_height=300, plot_width=400, x_axis_type='datetime')
sitter_confirmed_r = sitter_confirmed_p.line(x='x', y='confirmed_sits', source=sitter_onboarding_source, color="#2222aa", line_width=1)

# Create figure for sitter success graph
sitter_success_p = figure(title="New Sitter Success", plot_height=300, plot_width=400, x_axis_type='datetime')
sitter_success_r = sitter_success_p.line(x='x', y='is_successful', source=sitter_onboarding_source, color="#2222aa", line_width=1)
sitter_success_p.yaxis.formatter = NumeralTickFormatter(format="0%")

# Create figure for inactivity graph
sitter_inactivity_p = figure(title="New Sitter Inactivity Levels", plot_height=300, plot_width=400, x_axis_type='datetime')
sitter_inactivity_r = sitter_inactivity_p.line(x='x', y='inactive', source=sitter_onboarding_source, color="#2222aa", line_width=1)
sitter_inactivity_p.yaxis.formatter = NumeralTickFormatter(format="0%")

# Create figure for number of sitters graph
sitter_numbers_p = figure(title="New Sitter Numbers", plot_height=300, plot_width=400, x_axis_type='datetime')
sitter_numbers_r = sitter_numbers_p.line(x='x', y='num_sitters', source=sitter_onboarding_source, color="#2222aa", line_width=1)

sel_country2 = Select(title="Country:", options=country_options, value="All")
sel_country2.on_change('value', update_sitter_onboarding)

so_inputs = widgetbox(sel_country2)

sitter_onb_layout = gridplot([so_inputs, sitter_inactivity_p, sitter_apps_p, sitter_confirmed_p, sitter_numbers_p, sitter_success_p], ncols=3)
tab2 = Panel(child=sitter_onb_layout, title="Sitter Onboarding")
# additional tabs tab2, tab3....


###
###
### Start Owner success data manipulation

asgnmts = pd.read_csv('data_files/180201-assignments.csv', parse_dates=['created_date', 'start_date', 'end_date'])
asgnmts['is_assignment_filled'] = asgnmts.sid.notnull()

app_count = apps.groupby('assignment_id')['req_type'].count()
asgnmts.set_index('aid', inplace=True)
asgnmts['nb_applications'] = app_count

owners = pd.read_csv('data_files/180201-owners.csv', parse_dates=['joined_date', 'fst_start_date', 'start_date', 'expires_date', 'published_date'])
assignments_impr = pd.merge(asgnmts,
                            owners[['user_id','billing_country', 'fst_start_date']],
                            left_on='ouser_id', right_on='user_id')
assignments_impr['time_into_membership'] = assignments_impr.created_date - assignments_impr.fst_start_date

# select only assignments that were posted in first three months of membership
relevant_assignments = (
    assignments_impr[(assignments_impr.time_into_membership <= datetime.timedelta(days=90)) 
                     & (assignments_impr.time_into_membership >= datetime.timedelta(days=0))]
)

num_of_assignments = relevant_assignments['user_id'].value_counts()
num_confirmed_sitters = relevant_assignments.groupby('user_id')['is_assignment_filled'].sum()
num_apps = relevant_assignments.groupby('user_id')['nb_applications'].sum()

owners.set_index('user_id', inplace=True)
owners['nb_assignments'] = num_of_assignments
owners['nb_confirmed_sitters'] = num_confirmed_sitters
owners['nb_applications'] = num_apps
owners['is_successful'] = owners.nb_confirmed_sitters > 0
owners['nb_apps_per_assignment'] = owners.nb_applications / owners.nb_assignments
owners = owners.fillna(0)
owners.reset_index(inplace=True)
owners.set_index('fst_start_date', inplace=True)

num_owners = owners.groupby('fst_start_date')['user_id'].count()
num_owners_inactive = owners[owners.nb_assignments == 0].groupby('fst_start_date')['user_id'].count()
owner_activity = pd.concat([num_owners, num_owners_inactive], axis=1)
owner_activity.columns = ['num_owners', 'num_inactive']

owner_activity['percent_inactive'] = owner_activity.num_inactive / owner_activity.num_owners

def create_owner_onboarding_source(owner_data, owner_activity_data, assignment_data):

    sampled_owners = owner_data.loc[REPORT_START:REPORT_END].resample('M').agg({
        'nb_assignments': np.sum,
        'is_successful': np.mean
        }
    )
    sampled_active_owners = owner_data[owner_data.nb_assignments > 0].loc[REPORT_START:REPORT_END].resample('M').mean()
    sampled_activity = owner_activity_data.loc[REPORT_START:REPORT_END].resample('M').agg({
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
        confirmation_rate=sampled_assignments.is_assignment_filled)

    return source

owner_onboarding_source = ColumnDataSource(data=create_owner_onboarding_source(owners, owner_activity, relevant_assignments))


# Create figure for owner assignments graph
owner_assignments_p = figure(title="New Owner Assignments", plot_height=300, plot_width=400, x_axis_type='datetime')
owner_assignments_r = owner_assignments_p.line(x='x', y='nb_assignments', source=owner_onboarding_source, color="#2222aa", line_width=1)

# Create figure for owner apps per assignment graph
owner_apps_p = figure(title="Applications To New Owner Assignments", plot_height=300, plot_width=400, x_axis_type='datetime')
owner_apps_r = owner_apps_p.line(x='x', y='nb_apps_per_assignment', source=owner_onboarding_source, color="#2222aa", line_width=1)

# Create figure for owner success graph
owner_success_p = figure(title="New Owner Success", plot_height=300, plot_width=400, x_axis_type='datetime')
owner_success_r = owner_success_p.line(x='x', y='is_successful', source=owner_onboarding_source, color="#2222aa", line_width=1)
owner_success_p.yaxis.formatter = NumeralTickFormatter(format="0%")

# Create figure for owner numbers graph
owner_numbers_p = figure(title="New Owner Numbers", plot_height=300, plot_width=400, x_axis_type='datetime')
owner_numbers_r = owner_numbers_p.line(x='x', y='nb_owners', source=owner_onboarding_source, color="#2222aa", line_width=1)

# Create figure for owner inactivity graph
owner_inactive_p = figure(title="New Owner Inactivity", plot_height=300, plot_width=400, x_axis_type='datetime')
owner_inactive_r = owner_inactive_p.line(x='x', y='percent_inactive', source=owner_onboarding_source, color="#2222aa", line_width=1)
owner_inactive_p.yaxis.formatter = NumeralTickFormatter(format="0%")

# Create figure for confirmation rate graph
confirmation_rate_p = figure(title="New Owner Confirmation Rate", plot_height=300, plot_width=400, x_axis_type='datetime')
confirmation_rate_r = confirmation_rate_p.line(x='x', y='confirmation_rate', source=owner_onboarding_source, color="#2222aa", line_width=1)
confirmation_rate_p.yaxis.formatter = NumeralTickFormatter(format="0%")

#oo_inputs = widgetbox()

oo_layout = gridplot([owner_assignments_p, owner_apps_p, owner_success_p, owner_numbers_p, owner_inactive_p, confirmation_rate_p], ncols=3)
tab3 = Panel(child=oo_layout, title="Owner Onboarding")

# Layout of tabs for the whole dashboard
tabs = [tab1, tab2, tab3]

# Add tabs to curdoc
curdoc().add_root(Tabs(tabs=tabs))
curdoc().title = "Membership Growth & Ratio"