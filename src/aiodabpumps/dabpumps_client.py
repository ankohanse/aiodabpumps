"""client.py: DabPumps API for DAB Pumps integration."""

import httpx
import aiohttp
import logging

from datetime import datetime
from typing import Any
from yarl import URL

_LOGGER = logging.getLogger(__name__)


class DabPumpsClient_Base:
    """
    DabPumpsClient to communicate with DConnect or DAB Live servers
    """
    
    def __init__(self):
        pass

    
    @property
    def closed(self) -> bool:
        raise NotImplementedError("DabPumpsClientBase::is_closed")


    async def async_close(self):
        raise NotImplementedError("DabPumpsClientBase::_async_close")
    

    async def async_send_request(self, request):
        """
        GET or POST a request for JSON data.
        Also returns the request and response performed
        """
        raise NotImplementedError("DabPumpsClientBase::_async_send_request")
    

    async def async_get_cookie(self, domain:str, name:str):
        raise NotImplementedError("DabPumpsClientBase::_async_get_cookie")
    

    async def async_set_cookie(self, domain:str, name:str, value:Any):
        raise NotImplementedError("DabPumpsClientBase::_async_set_cookie")
    
    
    async def async_clear_cookies(self):
        raise NotImplementedError("DabPumpsClientBase::_async_clear_cookies")
    

class DabPumpsClient_Httpx(DabPumpsClient_Base):
    """
    DabPumpsClient to communicate with DConnect or DAB Live servers
    """

    def __init__(self, client:httpx.AsyncClient|None = None):
        self._asyncclient:httpx.AsyncClient = client or httpx.AsyncClient()
        self._client_owned = client == None


    @property
    def closed(self) -> bool:
        return self._asyncclient.is_closed


    async def async_close(self):
        if self._client_owned:
            await self._asyncclient.aclose()


    async def async_send_request(self, request):
        """
        GET or POST a request for JSON data.
        Also returns the request and response performed
        """
        # Perform the httpx request
        timestamp = datetime.now()

        req = self._asyncclient.build_request(
            method = request["method"],
            url = request["url"],
            params = request.get("params", None), 
            data = request.get("data", None),
            json = request.get("json", None),
            headers = request.get("headers", None)
        )
        rsp = await self._asyncclient.send(req)

        # Remember actual requests and response params, used for diagnostics
        _LOGGER.debug(f"rsp: {rsp}")

        request["headers"] = req.headers
        response = {
            "success": rsp.is_success,
            "status": f"{rsp.status_code} {rsp.reason_phrase}",
            "headers": rsp.headers,
            "elapsed": (datetime.now() - timestamp).total_seconds(),
        }
        if rsp.is_success and rsp.headers.get('content-type','').startswith('application/json'):
            response["json"] = rsp.json()
        else:
            response["text"] = rsp.text
        
        return (request,response)
    

    async def async_get_cookie(self, domain:str, name:str):
        return self._asyncclient.cookies.get(name, domain=domain)
    

    async def async_set_cookie(self, domain:str, name:str, value:Any):
        self._asyncclient.cookies.set(name, value=value, domain=domain, path='/')
    
    
    async def async_clear_cookies(self):
        self._asyncclient.cookies.clear()


class DabPumpsClient_Aiohttp(DabPumpsClient_Base):
    """
    DabPumpsClient to communicate with DConnect or DAB Live servers
    """

    def __init__(self, client:aiohttp.ClientSession|None = None):
        self._clientsession: aiohttp.ClientSession = client or aiohttp.ClientSession()
        self._client_owned = client == None


    @property
    def closed(self) -> bool:
        return self._clientsession.closed


    async def async_close(self):
        if self._client_owned:
            await self._clientsession.close()


    async def async_send_request(self, request):
        """
        GET or POST a request for JSON data.
        Also returns the request and response performed
        """
        # Perform the aiohttp request
        timestamp = datetime.now()
        flags = request.get("flags", {})

        async with self._clientsession.request(
            method = request["method"], 
            url = request["url"],
            params = request.get("params", None), 
            data = request.get("data", None), 
            json = request.get("json", None), 
            headers = request.get("headers", None),
            allow_redirects = flags.get("redirects", True)
        ) as rsp:

            # Remember actual requests and response params, used for diagnostics
            request["headers"] = rsp.request_info.headers
            response = {
                "success": rsp.ok,
                "status": f"{rsp.status} {rsp.reason}",
                "headers": rsp.headers,
                "elapsed": (datetime.now() - timestamp).total_seconds(),
            }
            if rsp.ok and rsp.headers.get('content-type','').startswith('application/json'):
                response["json"] = await rsp.json()
            else:
                response["text"] = await rsp.text()
            
            return (request,response)
        

    async def async_get_cookie(self, domain:str, name:str):
        url = URL(f"https://{domain}")
        cookies = self._clientsession.cookie_jar.filter_cookies(url)
        cookie = cookies.get(name, None)

        return cookie.value if cookie else None
    

    async def async_set_cookie(self, domain:str, key:str, value:Any):
        url = URL(f"https://{domain}")
        val = { key: value }
        self._clientsession.cookie_jar.update_cookies(val, url)
    
    
    async def async_clear_cookies(self):
        self._clientsession.cookie_jar.clear()
