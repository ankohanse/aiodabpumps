import asyncio
import json
import logging
import sys

from aiodabpumps import DabPumpsApi

# Setup logging to StdOut
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

TEST_USERNAME = "fill in your DConnect username here"
TEST_PASSWORD = "fill in your DConnect password here"
#
# Comment out the line below if username and password are set above
from tests import TEST_USERNAME, TEST_PASSWORD


async def main():
    api = None
    try:
        # Process these calls in the right order
        api = DabPumpsApi(TEST_USERNAME, TEST_PASSWORD)
        await api.async_login()

        # Retrieve installations accessible by this user
        install_map = await api.async_fetch_install_list()

        logger.info(f"installs: {len(install_map)}")

        for install_id, install in install_map.items():
            logger.info("")
            logger.info(f"installation: {install.name} ({install.id})")

            # Retrieve installation details
            device_map = await api.async_fetch_install_details(install_id)
            logger.info(f"devices: {len(device_map)}")

            for device_serial in device_map.keys():
                device = await api.async_fetch_device_details(device_serial)

                logger.info("")
                logger.info(f"device: {device.name} ({device.serial})")                
                for k,v in device._asdict().items():
                    logger.info(f"    {k}: {v}")
                                
                # Retrieve device config details
                config_id = device.config_id
                config = await api.async_fetch_device_config(config_id)

                logger.info("")
                logger.info(f"config: {config.description} ({config.id})")
                logger.info(f"    meta_params: {len(config.meta_params)}")             
                for k,v in config.meta_params.items():
                    logger.info(f"        {k}: {v}")

                # Once the calls above have been perfomed, the call below can be repeated periodically
                # Retrieve device statusses
                status_map = await api.async_fetch_device_statusses(device_serial)
                logger.info("")
                logger.info(f"statusses: {len(status_map)}")

                for k,v in status_map.items():
                    logger.info(f"    {v.key}: {v.val}")

    except Exception as e:
        logger.info(f"Unexpected exception: {e}")

    finally:
        if api:
            await api.async_close()


asyncio.run(main())  # main loop