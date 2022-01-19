from ftplib import error_perm
import threading
import logging
import dash
from dash import  html
from dash import dcc
import dash_bootstrap_components as dbc
import dash_trich_components as dtc
from dash import Input, Output, State
from dash_extensions.enrich import MultiplexerTransform, DashProxy
from .ws_netfield import NetFieldWebSocket, config
import asyncio
import pandas as pd
import plotly.graph_objs as go
import plotly.express as px


'''
store some temp variables to be shared between dash callbacks
'''
class Store(object):
    def __init__(self) -> None:
        super().__init__()
        self.data = pd.DataFrame()
        self.chart_position = 45
        self.data_flag = False
        self.add_chart = 1


'''
the constructor builds the layout and all dash callbacks are wrapped in a function
'''
class dashboard(config):
    def __init__(self) -> None:
        super().__init__()
        #DashProxy allows multiple IOs to the callbacks
        self.app = DashProxy(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
                            prevent_initial_callbacks=True, transforms=[MultiplexerTransform()])
        #silence callback exceptions because some components are added dynamically
        self.app.config.suppress_callback_exceptions=True
        self.build_base_layout()
        self.wrapped_callback(self.app) # the wrapper function
        self.ws = NetFieldWebSocket()
        self.store = Store()
            
    def build_base_layout(self):
        ##################################################################################
        #construct the logo and the sidebar
        #add hidden components which will be later dynamically allocated
        def base_layout():
            
            hidden_components= html.Div(
                children = [
                    dbc.Input(id = 'selected_device'),
                    dbc.Input(id = 'Topic')
                    ],
                hidden=True
                )

            side_bar = dtc.SideBar([
                            dtc.SideBarItem(
                                id = 'id_1',
                                label = "settings",
                                icon = "fas fa-cog"
                            ),
                            dtc.SideBarItem(
                                id = 'id_2',
                                label = "graphs", 
                                icon = "fas fa-chart-line"
                            ),
                            dcc.Interval(
                                id = 'interval-component',
                                interval = 3*1000, # in milliseconds
                                n_intervals = 0,
                                disabled = True
                            ),
                ],
                bg_color='red'
                )
            
            logo = html.Img(
                src = self.app.get_asset_url('Logo.png'),
                className='Logo'
                )

            return html.Div(id='basic_layout', children=[side_bar, logo, hidden_components])
        ##################################################################################
        
        ##################################################################################
        #construct a user form to authenticate app user either by username/password or API token
        def configuration_tab():
            user_form = html.Div(dbc.Toast([
                    dbc.Label('Email'),
                    dbc.Input(id = 'email'),
                    dbc.Label('Password',className = 'margin_label_top'),
                    dbc.Input(id = 'password',type = "password"),
                    dbc.Label('Orgenization ID',className = 'margin_label_top'),
                    dbc.Input(id = 'org_id'),
                    dbc.Label('API Endpoint',className = 'margin_label_top'),
                    dcc.Dropdown(id = 'api-endpoint', options = [
                        {'label' : 'training', 'value' : 'api-training'},
                        {'label' : 'production', 'value' : 'api'}
                    ]),
                    dbc.Label('API Key (Optional)', className = 'margin_label_top'),
                    dbc.Input(id = 'apikey', value = ''),
                    dbc.Button('Verify',id = 'btn_verify', className = 'verify_button'),
                    ],
                        header = 'netFIELD example APP',
                    ),id = "user_form", className = "user_form_container"
                )
            return html.Div(id = 'page1', children = [user_form])
        ##################################################################################
        
        
        ##################################################################################
        #construct the second page view
        def charts_tab():
            canvas = dbc.Offcanvas(
                children = [
                    dbc.Row(children = [
                        dbc.Col(
                        children = [
                            dbc.Label('Chart type: '),
                            dcc.Dropdown(id = 'chart_type', options = [
                                {'label': 'Line', 'value' : 'Line'},
                                {'label': 'Scatter', 'value' : 'Scatter'},
                                {'label': 'Bar', 'value' : 'Bar'},
                            ])
                        ]
                    ),
                    dbc.Col(
                        children = [
                            dbc.Label('X Axis: '),
                            dcc.Dropdown(id='X_point', options=[])
                        ]
                    ),
                    dbc.Col(
                        children = [
                            dbc.Label('Y Axis: '),
                            dcc.Dropdown(id='Y_point', options=[])
                        ]
                    ),

                    ]),
                    dbc.Row(
                        children = [
                            html.Div(children = [
                                dbc.Button(" Create", size = "lg", color = "success", className = "botton", id = 'creat_chart')],
                                className = 'create_chart_btn')
                        ]
                    )
                ],
                id = "offcanvas-placement",
                title = "Add a new chart!",
                is_open = False,
                placement = 'bottom'
            )
            
            return html.Div(id='page2', children = [
                dbc.Button(" Add a new chart",size = "lg", color = "secondary", className = "botton", id = 'add_chart_btn'),
                canvas
            ], hidden = True, className = 'add_chart_btn')
        ##################################################################################
        #final app layout (this is all static, dynamic components are added in the wrapped callbacks)                        
        self.app.layout = html.Div(children=[
        base_layout(), configuration_tab(), charts_tab()
        ])
    

    def wrapped_callback(self,app):
        
        ##################################################################################
        #Toggle between tabs by changing the hidden property of each page view
        @app.callback(
            Output('page1','hidden'),
            Output('page2', 'hidden'),
            Input('id_1','n_clicks'),
            Input('id_2', 'n_clicks'),
            )
        def toggle(_,__):
            ctx = dash.callback_context
            page1, page2 = True, True
            if 'id_1' in ctx.triggered[0]['prop_id']:
                return not page1, page2
            
            elif 'id_2' in ctx.triggered[0]['prop_id']:
                self.store.chart_position = 45
                
                return page1, not page2
            
            else:
                return dash.no_update
            
        ##################################################################################
        #Toggle between tabs by changing the hidden property of each page view
        @app.callback(
            Input('api-endpoint', 'value'),
            Output('api-endpoint', 'options')
        )
        def set_endpoint(value):
            if value  != 'None':
                self.config_file['BASE_API_ENDPOINT'] = f'wss://{value}.netfield.io/v1'
                self.update_config()
            return dash.no_update
        
        ##################################################################################
        #verify user input, add a component to the device view dynamically
        #TODO: a function should not be this long!
        @app.callback(
            Output('page1', 'children'),
            Input('btn_verify', 'n_clicks'),
            [
                State('email','value'),
                State('password','value'),
                State('apikey','value'),
                State('page1','children'),
                State('org_id', 'value')
            ]
        )
        def verify_mailpassword(_, email, password, apikey, children, org_id):
            #check user input and update config file
            if email and password:
                self.config_file['email'] = email
                self.config_file['password'] = password
                self.config_file['organisationId'] = org_id
                self.update_config()#save the scope to a configuration file for next sessions
                self.ws = asyncio.run(NetFieldWebSocket.from_email())
            
            elif apikey:
                self.config_file['accessToken'] = apikey
                self.update_config()
                self.ws = NetFieldWebSocket()
            
            #Fallback to configuration file
            else:
                if self.token:
                    self.ws = NetFieldWebSocket()                
                elif self.email and password:
                    self.ws = asyncio.run(NetFieldWebSocket.from_email())
                else:
                    msg = msg_bar(error=1, msg='No configuration found...')
                    children.append(msg)
                    return children
                
            verify_user = asyncio.run(self.ws.verify_token())
            if verify_user:
                msg = msg_bar(error = 1, msg=f'ERROR : {verify_user}')
                children.append(msg)
                return children
            
            #create a device list radio items
            try:
                devices = asyncio.run(self.ws.get_device_list())
                devices = [{'label' : device['name'], 'value' : device['id']} for device in devices]
                device_list = html.Div(children = [
                    dbc.Toast(
                        children = [
                            dcc.RadioItems(options = devices, value = devices[0]['value'], id = 'selected_device'),
                            dbc.Label('Topic:', className = 'margin_label_top'),
                            dbc.Input(id = 'Topic', className = 'margin_label_top')
                        ],
                        header = 'Onboarded Devices'
                    ),
                    ],
                        id = 'device_list', className = 'user_form_container'
                    )
                children.append(device_list)
                children[0]['props']['className'] = 'user_form_container_left'
                msg = msg_bar(error=0, msg='User verified...!')
                children.append(msg)
            except Exception as ex:
                msg = msg_bar(error=1, msg=f'Exception : {ex}')
                children.append(msg)
            return children
        

        ##################################################################################
        # when switched to page2 view, activate an update interval
        @app.callback(
            Input('id_2', 'n_clicks'),
            Output('interval-component', 'disabled'),
        )
        def activate_interval(_):
            return False
        
        ##################################################################################
        # when switched to page1 view, reset data flag to disconnect the websocket
        @app.callback(
            Input('id_1', 'n_clicks'),
            Output('page2', 'children')
        )
        def reset_data_flag(_):
            self.store.data_flag = True
            return dash.no_update
    
        ########################    
        #workaround to calling async functions from a dash callback
        # an endless loop that collects data from the websocket, and assigns it to the current store scope    
        def data_collector(id, topic):
            async def wrapper():
                await self.ws.init_websocket()
                await self.ws.subscribe_to_topic(id, topic)
                await self.ws.listen_for_messages()
                async for msg in self.ws.ws:
                    tmp = await self.ws.listen_for_messages()
                    if 'message' in tmp.keys():
                        self.store.data = self.store.data.append(tmp['message']['data'], ignore_index=True)
                    if self.store.data_flag:
                        break
                await self.ws.close_websocket()
            try:
                asyncio.run(wrapper())
            except (Exception, KeyboardInterrupt) as ex:
                logging.error(ex)
            return
        ########################
        
        
            
        ##################################################################################
        #when switched to page2 view, the websocket connection is initiated, and a sub is made
        @app.callback(
            Input('interval-component', 'disabled'),
            Output('page2', 'children'),
            [
                State('selected_device', 'value'),
                State('Topic', 'value')
            ]
        )
        def init_socket(disabled, id, topic):
            if not disabled:
                try:
                    self.store.data_flag = False
                    if not topic or not id:
                        logging.info('device Id or topic is missing....')
                        return dash.no_update
                    self.config_file['message-topic'] = topic
                    self.config_file['device'] = id
                    self.update_config()                      
                    sub = threading.Thread(target=data_collector, args=(id, topic))
                    sub.start()
                except Exception as ex:
                    logging.exception(ex)
            return dash.no_update
                


        ##################################################################################
        #when switching back to page view 1, disable the interval update component
        @app.callback(
            Input('id_1', 'n_clicks'),
            Output('interval-component', 'disabled'),
        )
        def deactivate_interval(click):
            if click:
                return True
            
        ##################################################################################
        #active on button add new chart, the canvass prop 'is_open' is set
        #the plot axis options are added from the dataframe in the store
        @app.callback(
            Input('add_chart_btn', 'n_clicks'),
            Output('offcanvas-placement', 'is_open'),
            Output('X_point', 'options'),
            Output('Y_point', 'options'),
        )
        def show_canvas(_):            
            features = self.store.data.columns
            options = [
                {'label' : key, 'value' : key}
                for key in features
            ]
            return True, options, options
        
        ##################################################################################
        # active on button create chart, reads the state of page2 children. (children are represented by a list and charts start at 2) 
        # read the state of the dropdown for the axis
        # ! since the update_chart callback alters the state of page2, the number of times 
        # ! the create button was hit is tracked, and used to initate the callback 
        @app.callback(
            Input('creat_chart', 'n_clicks'),
            Output('page2', 'children'),
            [
                State('X_point', 'value'),
                State('Y_point', 'value'),
                State('chart_type', 'value'),
                State('page2', 'children'),
            ]
        )
        def add_chart(_, x_label, y_label, chart_type,children):
            if _ == self.store.add_chart:
                if not x_label and not y_label:
                    return dash.no_update
                self.store.add_chart += 1
                fig = None
                if chart_type == 'Line':
                    fig = draw_line(x_label, y_label)
                elif chart_type == 'Scatter':
                    fig = draw_scatter(x_label, y_label)
                elif chart_type == 'Bar':
                    fig = draw_bar(x_label, y_label)
                
                children.append(
                    dcc.Graph(figure = fig, className = 'first_chart', style = {'margin-top' : f'{self.store.chart_position}%'})
                )
                #//future charts should placed at a higher top-margin value
                self.store.chart_position+=235
                return children
            return dash.no_update

        ##################################################################################
        # loop through the children list
        # update the x,y properties
        @app.callback(
            Output('page2', 'children'),
            Input('interval-component', 'n_intervals'),
            [
                State('page2', 'children')
            ]
        )
        def update_chart(_, children):
            for idx in range(2,len(children)):
                labels = children[idx]['props']['figure']['data'][0]['hovertemplate'].split("=%{x}<br>")
                x_label = labels[0]
                y_label = labels[1][0:labels[1].index('=')]
                X = self.store.data[x_label].to_list()
                y = self.store.data[y_label].to_list()
                children[idx]['props']['figure']['data'][0]['x'] = X
                children[idx]['props']['figure']['data'][0]['y'] = y
            return children


        ##############################
        #plot types
        def draw_scatter(X,y):
            return px.scatter(data_frame= self.store.data,x=X, y=y)
        
        def draw_line(X,y):
            return px.line(data_frame=self.store.data, x=X, y=y)
        
        def draw_bar(X,y):
            return px.bar(data_frame=self.store.data, x=X, y=y)
        ##############################
        
        ##############################
        # notifications
        def msg_bar(error=0, msg=None):
            if error:
                message_bar = dbc.Alert(msg,dismissable=True,
                is_open=True,className='alet-bar',color='danger')
                return message_bar
            else:
                message_bar = dbc.Alert(msg,dismissable=True,
                is_open=True,className='alet-bar',color='success')
                return message_bar
        ##############################