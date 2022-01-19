import json, logging, os
from typing import Optional
import httpx, uuid
import inspect
import websockets
import base64

DEFAULT_LOG_LEVEL = "DEBUG"
LOG_LEVEL = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=LOG_LEVEL)
api_urls = {
    "authentication" : '/auth',
    "verification" : '/auth/verify',
    "Revoke" : '/auth/revoke',
    "Devices" : '/devices'
}

class config:
    def __init__(self) -> None:
        self.current_dir = os.path.dirname(
            os.path.abspath(
                inspect.getfile(inspect.currentframe())
            )
        )
        self.config_file = json.load(
            open(self.current_dir+'/assets/config.json')
        )
        self.email = self.config_file['email']
        self.password = self.config_file['password']
        self.token = self.config_file['accessToken']
        self.BASE_API_ENDPOINT = self.config_file['BASE_API_ENDPOINT']
        self.topic = self.config_file['message-topic']
        self.device_id = self.config_file['device']
        self.organizationId = self.config_file['organisationId']
    
    def update_config(self):
        logging.debug('updating config')
        with open(self.current_dir+'/assets/config.json','w') as f:
            json.dump(self.config_file,f)
        self.__init__()

class NetFieldWebSocket(config):
    ''' Websocket communication with netFIELD'''
    def __init__(self) -> None:
        super().__init__()
        self.ws : Optional[websockets.WebSocketClientProtocol] = None
        self.auth = {'auth' : {'headers':{}}}
        self.auth['headers'] = {
                "authorization": self.token
            }
    
    @classmethod
    async def from_email(cls):
        await cls._gen_access_token(NetFieldWebSocket())
        return cls()
           
    async def init_websocket(self):
        try:
            self.ws = await websockets.connect(self.BASE_API_ENDPOINT, ping_interval=None)
            await self._send_hello()
            res = await self.ws.recv()
            logging.debug(res)
            return 1
        except Exception as ex:
            logging.exception(ex)
            return 0
        
    async def verify_token(self):
        endpoint = f"{self.BASE_API_ENDPOINT.replace('wss','https')}/auth/verify"
        async with httpx.AsyncClient() as client:
            resp = await client.get(endpoint, headers=self.auth['headers'])
            try:
                resp = resp.json()
                if 'error' in resp.keys():
                    return resp["message"]
            except:
                return 0
        
    async def close_websocket(self):
        if self.ws:
            await self.ws.close()
            await self.ws.wait_closed()
            logging.debug('socket closed')
        
    async def _gen_access_token(self):
        payload = {
            "grantType" : "password",
            "email" : self.email,
            "password" : self.password
        }
        api_endpoint = f"{self.BASE_API_ENDPOINT.replace('wss', 'https')}/auth"
        async with httpx.AsyncClient() as client:
            try:
                _resp = await client.post(api_endpoint, data=payload)
                _resp = _resp.json()
                self.config_file["accessToken"] = _resp["accessToken"]
                self.update_config()
            except Exception as ex:
                logging.exception(ex)
                raise(ex)
 
    async def _send_hello(self):
        hello_msg = {
            "type": "hello",
            "id": self.device_id,
            "version": "2",
            "auth": self.auth
        }
        await self._send_json(hello_msg)
    
    async def _send_json(self,msg):
        if self.ws:
            await self.ws.send(
                json.dumps(msg)
            )

    async def get_device_list(self):
        query = {"organisationId" : self.organizationId}
        header = {"authorization" : self.token}
        endpoint = f"{self.BASE_API_ENDPOINT.replace('wss', 'https')}/devices"
        async with httpx.AsyncClient() as client:
            try:
                _resp = await client.get(endpoint, headers=header,params=query)
                _resp = _resp.json()
                device_list = [device for device in _resp['devices']]
                return device_list
            except Exception as ex:
                logging.info(ex)
            
    async def subscribe_to_topic(self, deviceId: str, topic : str):
        try:
            topic = base64.b64encode(topic.encode('ascii')).decode()
            path = f'/devices/{deviceId}/platformconnector/{topic}'
            msg = {
                "type" : "sub",
                "id" : str(uuid.uuid4()),
                "path" : path
            }
            if self.ws:
                await self._send_json(msg)
                msg = await self.ws.recv()
                logging.info('Subscribed to topic in config file')
        except Exception as ex:
            logging.exception(ex)
            
    async def listen_for_messages(self):
        if self.ws:
            msg = await self.ws.recv()
            return await self.on_message_handler(msg)
            
    async def on_message_handler(self, message_raw):
        try:
            msg = json.loads(message_raw)
            return msg
        except Exception as inst:
            logging.exception(inst)
            return 0
    async def endless_msg_handler(self):
        for msg in self.ws:
            m = await self.listen_for_messages()
    
    def isConnected(self):
        return self.ws.state