from flask import render_template, flash, redirect, url_for, request
from app import app, auth

import numpy as np
import pandas as pd
import datetime
import calendar
from time import strftime
from dateutil.relativedelta import relativedelta

from bokeh.io import curdoc
from bokeh.plotting import figure, show
from bokeh.layouts import row, column, widgetbox, gridplot
from bokeh.models import ColumnDataSource, DatetimeTickFormatter, NumeralTickFormatter, HoverTool
from bokeh.palettes import brewer
from bokeh.models.widgets import Select, Div, Panel
from bokeh.embed import components

# Global settings
TOOLS = "pan,wheel_zoom,box_zoom,reset"
REPORT_START = '01-Jan-2016' # Earliest point for all plots
REPORT_END = '30-Nov-2017' # End point for onboarding reports, usually 3 months in the past
TOP_MARKETS = ['United Kingdom','United States', 'Australia', 'Canada', 'New Zealand']
COUNTRY_OPTIONS = ["All", "United Kingdom", "United States", "Australia", "Canada", "New Zealand", "ROW"]

## Growth data manipulation ##
def manipulate_numactive(country):
    member_numbers = pd.read_csv('app/data_files/180301-num-active.csv', parse_dates=(['period']))
    member_numbers = (member_numbers.groupby(['period', 'country', 'membership_type'])['num_active']
            .sum()
            .unstack() # unstack the membership_type column
    ).reset_index()

    member_numbers['country_cat'] = [x if x in TOP_MARKETS else 'ROW' for x in member_numbers['country']]
    member_numbers.fillna(0, inplace=True)
    member_numbers[['homeowner', 'housesitter', 'combined']] = member_numbers[['homeowner', 'housesitter', 'combined']].astype(int)

    if (country != "All"):
        member_numbers = member_numbers[member_numbers.country_cat == country]

    # Set an inital state for plotting all member data
    all_members = member_numbers.groupby('period')[['homeowner', 'housesitter', 'combined']].sum().reset_index()

    return all_members

def create_growth_source(data):
    source = dict(
        x=data.period,
        Owners=data.homeowner,
        Sitters=data.housesitter,
        Combined=data.combined,
        datestr=[d.strftime("%d-%m-%Y") for d in data.period])

    return source

def visualise_growth(source):
    p = figure(title="Membership Growth", plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label="Members", tools=TOOLS)

    for idx, member in enumerate(['Owners', 'Sitters', 'Combined']):
        g1 = p.line(x='x', y=member, source=source, legend="Membership = {}".format(member), color=brewer['Dark2'][3][idx], line_width=2)

    p.add_tools(HoverTool(renderers=[g1], show_arrow=False, line_policy='next', tooltips=[
            ('Owners', '@Owners'),
            ('Sitters', '@Sitters'),
            ('Combined', '@Combined'),
            ('Date',  '@datestr')],
        mode='vline'
        )
    )

    p.legend.location = "top_left"

    return p

def create_ratio_source(data):
    source = dict(
        x=data.period,
        y=data.housesitter / data.homeowner,
        datestr=[d.strftime("%d-%m-%Y") for d in data.period])
    return source

def generate_counts_html(source):

    last_count = (source.data['Owners'].shape[0]) - 1
    owner_count = (source.data['Owners'][last_count]).astype('str')
    sitter_count = (source.data['Sitters'][last_count]).astype('str')
    combined_count = (source.data['Combined'][last_count]).astype('str')
    
    text = str("<ul><li>" + owner_count + " Owners</li>" + "<li>" + sitter_count + " Sitters </li>"  + "<li>" + combined_count + " Combined</li></ul>")
    
    return text


### Sitter success data manipulation ###

def manipulate_sitters_apps(country):
    apps = pd.read_csv('app/data_files/180301-applications.csv', parse_dates=['date_created', 'last_modified'])
    sitters = pd.read_csv('app/data_files/180301-sitters.csv', parse_dates=['fst_start_date', 'start_date', 'expires_date'])

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

    sitter_data = sitters[['user_id', 'fst_start_date', 'billing_country']].copy()
    sitter_data.set_index('user_id', inplace=True)

    # Additional columns and indexing
    sitter_data['nb_applications'] = num_of_apps
    sitter_data['confirmed_sits'] = num_confirmed
    sitter_data['is_successful'] = sitter_data.confirmed_sits > 0
    sitter_data['country_cat'] = [x if x in TOP_MARKETS else 'ROW' for x in sitter_data['billing_country']]
    sitter_data.reset_index(inplace=True)
    sitter_data.set_index('fst_start_date', inplace=True)
    sitter_data = sitter_data.fillna(0)

    if (country == "All"):
        return apps, sitter_data
    else:
        return apps, sitter_data[sitter_data.country_cat == country]

def manipulate_sitter_verif(sitter_data):
    st_verif = pd.read_csv('app/data_files/180313-standard-verif.csv', parse_dates=['standard_verif'])
    sitter_verif = sitter_data.reset_index().merge(st_verif, how='left', on='user_id')

    sitter_verif['verif_in_one_month'] = (sitter_verif.standard_verif - sitter_verif.fst_start_date) <= datetime.timedelta(days=30)

    return sitter_verif

def create_sitter_verif_source(data):
    sampled_sitters = data.set_index('fst_start_date').loc[REPORT_START:REPORT_END].verif_in_one_month.resample('M').mean()

    source = dict(
        x=sampled_sitters.index,
        y=sampled_sitters,
        datestr=[d.strftime("%d-%m-%Y") for d in sampled_sitters.index])

    return source

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

### Owner success data manipulation ###

def manipulate_owner_assignments(apps, country):
    asgnmts = pd.read_csv('app/data_files/180301-assignments.csv', parse_dates=['created_date', 'start_date', 'end_date'])
    asgnmts['is_assignment_filled'] = asgnmts.sid.notnull()

    app_count = apps.groupby('assignment_id')['req_type'].count()
    asgnmts.set_index('aid', inplace=True)
    asgnmts['nb_applications'] = app_count

    owners = pd.read_csv('app/data_files/180301-owners.csv', parse_dates=['joined_date', 'fst_start_date', 'start_date', 'expires_date', 'published_date'])
    assignments_impr = pd.merge(asgnmts,
                                owners[['user_id','billing_country', 'fst_start_date']],
                                left_on='ouser_id', right_on='user_id')
    assignments_impr['time_into_membership'] = assignments_impr.created_date - assignments_impr.fst_start_date

    # select only assignments that were posted in first three months of membership
    relevant_assignments = (
        assignments_impr[(assignments_impr.time_into_membership <= datetime.timedelta(days=90)) 
                         & (assignments_impr.time_into_membership >= datetime.timedelta(days=0))]
    ).copy()
    relevant_assignments['country_cat'] = [x if x in TOP_MARKETS else 'ROW' for x in relevant_assignments['billing_country']]


    num_of_assignments = relevant_assignments['user_id'].value_counts()
    num_confirmed_sitters = relevant_assignments.groupby('user_id')['is_assignment_filled'].sum()
    num_apps = relevant_assignments.groupby('user_id')['nb_applications'].sum()

    owners.set_index('user_id', inplace=True)
    owners['nb_assignments'] = num_of_assignments
    owners['nb_confirmed_sitters'] = num_confirmed_sitters
    owners['nb_applications'] = num_apps
    owners['is_successful'] = owners.nb_confirmed_sitters > 0
    owners['nb_apps_per_assignment'] = owners.nb_applications / owners.nb_assignments
    owners['country_cat'] = [x if x in TOP_MARKETS else 'ROW' for x in owners['billing_country']]
    owners = owners.fillna(0)
    owners.reset_index(inplace=True)
    owners.set_index('fst_start_date', inplace=True)

    if (country == "All"):
        return asgnmts, relevant_assignments, owners
    else:
        return asgnmts, relevant_assignments[relevant_assignments.country_cat == country], owners[owners.country_cat == country]


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

### Network Health data manipulation ###

def manipulate_full_data(asgnmts, apps):
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

    date_index = pd.date_range(REPORT_START, nh_applications.created_date.max(), freq='1M')-pd.offsets.MonthEnd(1)

    return nh_applications, nh_assignments, date_index

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

    
    df = pd.DataFrame(data=values, index=date_index)

    # broadcast new calculated columns
    df['assignments_per_owner'] = df.assignments / df.owners
    df['apps_per_assignment'] = df.applications / df.assignments
    df['owner_success'] = df.successful_owners / df.owners
    df['confirmation_rate'] = df.filled_assignments / df.assignments
    df['sits_per_sitter'] = (df.filled_assignments / df.sitters)
    df['sitter_success'] = df.successful_sitters / df.sitters
    df['member_ratio'] = df.sitters / df.owners

    return df

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

def visualise(source, field_list, title_list, axis_list, format_list, percent_list):

    plots = [] # new list for all plots

    # loop through the list of plot settings
    for field, title, label, format, percent in zip(field_list, title_list, axis_list, format_list, percent_list):

        tooltip = '@'+field+format # create the tooltip

        p = figure(title=title, plot_height=300, plot_width=1000, x_axis_type='datetime', y_axis_label=label, tools=TOOLS)
        p.line(x='x', y=field, source=source, color=brewer['Dark2'][7][4], line_width=2)
        p.add_tools(HoverTool(line_policy='next', tooltips=[
                (label, tooltip),
                ('Date',  '@datestr'),]
            , mode='vline')
        )

        # format y axis as percentage if neccessary
        if(percent == True):
            p.yaxis.formatter = NumeralTickFormatter(format="0%")

        plots.append(p)

    return plots


# Index page, no args
@app.route('/')
@auth.login_required
def index():

    return render_template("index.html", title='Home')


# Membership Growth page, no args
@app.route('/membership-growth')
@auth.login_required
def membership_growth():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create the growth DataSources and plot
    all_members = manipulate_numactive(current_country)
    growth_source = ColumnDataSource(data=create_growth_source(all_members))
    growth_plot = visualise_growth(growth_source)
    a_number = Div(text=generate_counts_html(growth_source), width=200, height=100)

    # Set up layouts
    growth_inputs = row(a_number)
    growth_layout = column(growth_plot, growth_inputs, width=1200)

    script, div = components(growth_layout)
    return render_template("membership-growth.html",
        title='Membership Growth',
        script=script, div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# Membership Growth page, no args
@app.route('/membership-ratio')
@auth.login_required
def membership_ratio():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create the growth DataSources and plot
    all_members = manipulate_numactive(current_country)
    ratio_source = ColumnDataSource(data=create_ratio_source(all_members))
    
    var_list = ['y']
    title_list = ['Membership Ratio']
    axis_labels = ['Ratio']
    number_formats = ['{0.00}']
    is_percents = [False]

    plots = visualise(ratio_source, var_list, title_list, axis_labels, number_formats, is_percents)

    growth_source = ColumnDataSource(data=create_growth_source(all_members))
    a_number = Div(text=generate_counts_html(growth_source), width=200, height=100)

    # Set up layouts and add to tab1
    #growth_inputs = row(a_number)
    growth_layout = column(plots)

    script, div = components(growth_layout)
    return render_template("membership-ratio.html",
        title='Membership Ratio',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New sitter success page, no args
@app.route('/new-sitter-success')
@auth.login_required
def new_sitter_success():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create sitter onboarding datasource and plots
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)
    sitter_onboarding_source = ColumnDataSource(data=create_sitter_onboarding_source(onboarding_sitters))
    
    var_list = ['is_successful', 'confirmed_sits']
    title_list = ['New Sitter Success', 'Sits Per New Sitter']
    axis_labels = ['Success rate', 'Sits']
    number_formats = ['{0%}', '{0.00}']
    is_percents = [True, False]

    plots = visualise(sitter_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layout
    sitter_onb_layout = column(plots)

    script, div = components(sitter_onb_layout)
    return render_template("new-sitter-success.html",
        title='New Sitter Success',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New sitter activity page, no args
@app.route('/new-sitter-activity')
@auth.login_required
def new_sitter_activity():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create sitter onboarding datasource and plots
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)
    sitter_onboarding_source = ColumnDataSource(data=create_sitter_onboarding_source(onboarding_sitters))
    
    var_list = ['nb_applications', 'percent_inactive']
    title_list = ['New Sitter Applications', 'New Sitter Inactivity']
    axis_labels = ['Applications', 'Percent Inactive']
    number_formats = ['{0}', '{0%}']
    is_percents = [False, True]

    plots = visualise(sitter_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layout
    sitter_onb_layout = column(plots)

    script, div = components(sitter_onb_layout)
    return render_template("new-sitter-activity.html",
        title='New Sitter Activity',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New sitter activity page, no args
@app.route('/new-sitter-volume')
@auth.login_required
def new_sitter_volume():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create sitter onboarding datasource and plots
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)
    sitter_onboarding_source = ColumnDataSource(data=create_sitter_onboarding_source(onboarding_sitters))
    
    var_list = ['num_sitters']
    title_list = ['New Sitters']
    axis_labels = ['Sitters']
    number_formats = ['{0}']
    is_percents = [False]

    plots = visualise(sitter_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layout
    sitter_onb_layout = column(plots)

    script, div = components(sitter_onb_layout)
    return render_template("new-sitter-volume.html",
        title='New Sitter Volume',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New sitter activity page, no args
@app.route('/new-sitter-verif')
@auth.login_required
def new_sitter_verif():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # Create sitter onboarding datasource and plots
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)
    sitters_with_verif = manipulate_sitter_verif(onboarding_sitters)
    sitter_verif_source = create_sitter_verif_source(sitters_with_verif)

    var_list = ['y']
    title_list = ['New Sitter Verification']
    axis_labels = ['Percent Verified']
    number_formats = ['{0%}']
    is_percents = [True]

    plots = visualise(sitter_verif_source, var_list, title_list, axis_labels, number_formats, is_percents)

    sitter_v_layout = column(plots)

    script, div = components(sitter_v_layout)
    return render_template("new-sitter-verif.html",
        title='New Sitter Verification',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New Owner success page, no args
@app.route('/new-owner-success')
@auth.login_required
def new_owner_success():

     # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    # Create owner onboarding datasource and plots
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)
    owner_onboarding_source = ColumnDataSource(data=create_owner_onboarding_source(owners, relevant_assignments))
    
    var_list = ['is_successful', 'confirmation_rate']
    title_list = ['New Owner Success', 'New Owner Confirmation Rate']
    axis_labels = ['Success rate', 'Confirmation rate']
    number_formats = ['{0%}', '{0%}']
    is_percents = [True, True]

    plots = visualise(owner_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layouts and add to tab3
    oo_layout = column(plots)

    script, div = components(oo_layout)
    return render_template("new-owner-success.html",
        title='New Owner Success',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New Owner success page, no args
@app.route('/new-owner-activity')
@auth.login_required
def new_owner_activity():

     # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    # Create owner onboarding datasource and plots
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)
    owner_onboarding_source = ColumnDataSource(data=create_owner_onboarding_source(owners, relevant_assignments))
    
    var_list = ['nb_assignments', 'percent_inactive']
    title_list = ['New Owner Assignments', 'New Owner Inactivity']
    axis_labels = ['Assignments', 'Percent Inactive']
    number_formats = ['{0}', '{0%}']
    is_percents = [False, True]

    plots = visualise(owner_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layouts and add to tab3
    oo_layout = column(plots)

    script, div = components(oo_layout)
    return render_template("new-owner-activity.html",
        title='New Owner Activity',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# New Owner success page, no args
@app.route('/new-owner-volume')
@auth.login_required
def new_owner_volume():

     # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    # Create owner onboarding datasource and plots
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)
    owner_onboarding_source = ColumnDataSource(data=create_owner_onboarding_source(owners, relevant_assignments))
    
    var_list = ['nb_owners']
    title_list = ['New Owners']
    axis_labels = ['Owners']
    number_formats = ['{0}']
    is_percents = [False]

    plots = visualise(owner_onboarding_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layouts and add to tab3
    oo_layout = column(plots)

    script, div = components(oo_layout)
    return render_template("new-owner-volume.html",
        title='New Owner Volume',
        script=script,
        div=div,
        country_names=COUNTRY_OPTIONS,
        current_country=current_country)

# Active sitter page, no args
@app.route('/active-sitter-success')
@auth.login_required
def active_sitter_success():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    #Get asgnmts
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)

    # Create rolling datasource and plots
    nh_applications, nh_assignments, nh_index = manipulate_full_data(asgnmts, apps)
    rolling_data = calculate_rolling(nh_applications, nh_assignments, nh_index)
    rolling_data_source = ColumnDataSource(data=create_rolling_data_source(rolling_data))
    
    var_list = ['sitter_success', 'sits_per_sitter']
    title_list = ['Active Sitter Success', 'Sits Per Active Sitter']
    axis_labels = ['Success rate', 'Sits']
    number_formats = ['{0%}', '{0.00}']
    is_percents = [True, False]

    plots = visualise(rolling_data_source, var_list, title_list, axis_labels, number_formats, is_percents)

    nh_layout = column(plots)

    script, div = components(nh_layout)
    return render_template("active-sitter-success.html",
        title='Active Sitter Success',
        script=script,
        div=div)

# Active owner page, no args
@app.route('/active-owner-success')
@auth.login_required
def active_owner_success():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    #Get asgnmts
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)

    # Create rolling datasource and plots
    nh_applications, nh_assignments, nh_index = manipulate_full_data(asgnmts, apps)
    rolling_data = calculate_rolling(nh_applications, nh_assignments, nh_index)
    rolling_data_source = ColumnDataSource(data=create_rolling_data_source(rolling_data))
    
    var_list = ['owner_success', 'confirmation_rate']
    title_list = ['Active Owner Success', 'Confirmation Rate']
    axis_labels = ['Success rate', 'Confirmation rate']
    number_formats = ['{0%}', '{0%}']
    is_percents = [True, True]

    plots = visualise(rolling_data_source, var_list, title_list, axis_labels, number_formats, is_percents)

    nh_layout = column(plots)

    script, div = components(nh_layout)
    return render_template("active-owner-success.html",
        title='Active Owner Success',
        script=script,
        div=div)

# Active owner page, no args
@app.route('/active-member-ratio')
@auth.login_required
def active_member_ratio():

    # Look for country in the URL
    current_country = request.args.get("country")
    if current_country == None:
        current_country = "All"

    # get apps data
    apps, onboarding_sitters = manipulate_sitters_apps(current_country)

    #Get asgnmts
    asgnmts, relevant_assignments, owners = manipulate_owner_assignments(apps, current_country)

    # Create rolling datasource and plots
    nh_applications, nh_assignments, nh_index = manipulate_full_data(asgnmts, apps)
    rolling_data = calculate_rolling(nh_applications, nh_assignments, nh_index)
    rolling_data_source = ColumnDataSource(data=create_rolling_data_source(rolling_data))

    var_list = ['member_ratio']
    title_list = ['Active Member Ratio']
    axis_labels = ['Ratio']
    number_formats = ['{0.00}']
    is_percents = [False]

    plots = visualise(rolling_data_source, var_list, title_list, axis_labels, number_formats, is_percents)

    # Set up layouts and add to tab4
    nh_layout = column(plots)

    script, div = components(nh_layout)
    return render_template("active-member-ratio.html",
        title='Active Member Ratio',
        script=script,
        div=div)