import asyncio
import copy
import logging
import pytest
import pytest_asyncio

from aiodabpumps import DabPumpsClient_Httpx, DabPumpsClient_Aiohttp

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, mode, url, exp_text, exp_json",
    [
        ("get text", "x", "https://github.com",    True,  False),
        ("get json", "x", "https://api.github.com/repos/ankohanse/aioxcom/issues", False, True),

        ("get text", "a", "https://github.com",     True,  False),
        ("get json", "a", "https://api.github.com/repos/ankohanse/aioxcom/issues", False, True),
    ]
)
async def test_get(name, mode, url, exp_text, exp_json):
    match mode:
        case "x": client = DabPumpsClient_Httpx()
        case "a": client = DabPumpsClient_Aiohttp()
        case _: assert False, "incorrect mode parameter for test_connect"

    req = {
        "method": "GET",
        "url": url,
        "headers": { "Accept": "*/*" }
    }

    assert not client.closed
   
    (request,response) = await client.async_send_request(req)

    assert request["method"] == req["method"]
    assert request["url"] == req["url"]
    assert "params" not in request
    assert "data" not in request
    assert "json" not in request
    assert "headers" in request

    _LOGGER.debug(f"response: {response}")
    assert response["success"] == True

    if exp_text:
        assert "text" in response
    else:
        assert "text" not in response
    
    if exp_json:
        assert "json" in response
    else:
        assert "json" not in response

    # Check close behavior as well
    assert not client.closed
    await client.async_close()
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, mode, url, exp_success, exp_text, exp_json",
    [
        ("get fail", "x", "http://does.not.exist", False, False, False),

        ("get fail", "a", "http://does.not.exist", False, False, False),
    ]
)
async def test_fail(name, mode, url, exp_success, exp_text, exp_json):
    match mode:
        case "x": client = DabPumpsClient_Httpx()
        case "a": client = DabPumpsClient_Aiohttp()
        case _: assert False, "incorrect mode parameter for test_connect"

    req = {
        "method": "GET",
        "url": url,
    }

    with pytest.raises(Exception) as e_info:
        (request,response) = await client.async_send_request(req)

        
    # Check close behavior as well
    assert not client.closed
    await client.async_close()
    assert client.closed


