[![license](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)
[![buy_me_a_coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/ankohanse)


# aiodabpumps

Python library for retrieving sensor information from DAB Pumps devices.
This component uses webservices to connect to the DAB Pumps DConnect website and automatically determines which installations and devices are available there.

The custom component was tested with a ESybox 1.5kw combined with a DConnect Box 2. It has also been reported to function correctly for ESybox Mini and ESybox Diver.

Disclaimer: this library is NOT created by DAB Pumps


# Prerequisites
This device depends on the backend servers for the DAB Pumps DAB Live app and DConnect app to retrieve the device information from.

- For ESybox Mini3 pumps:

  These are supported on the DAB Live app with a free DAB Live account, or on the DConnect App with a paid account. Follow the steps under either [DAB Live](#dab-live) or [DConnect](#dconnect).

- For other pumps:

  To see whether your pump device is supported via DConnect, browse to [internetofpumps.com](https://internetofpumps.com/), select 'Professional Users' and scroll down to the operation diagram. Some pump devices will have integrated connectivity (Esybox MAX and Esybox Mini), others might require a DConnect Box/Box2 device (Esybox and Esybox Diver). A free trial period is available, after that there is a yearly subscription to DAB Pumps DConnect (US$ 20 in 2024). Follow the steps under [DConnect](#dconnect).

## DAB Live
If you have a pump that is supported for DAB Live then:
- Download the DAB Live app on your phone or tablet
- Open the app and create a new account. When asked between 'Professional' or 'End User' either are good, this has no implications on the app or the use of this library.
- Remember the email address and password for the account as these are needed in any script using this library.
- Follow the steps in the app to register your pump.

## DConnect
If you have a device that is supported for DConnect then:
- Enable your DAB Pumps devices to connect to DConnect. For more information on this, see the manual of your device.
- Install the DConnect app, or open the DConnect website in a browser.
- Setup an account for DConnect, see the remarks under 'DConnect Account' below.
- Remember the email address and password for the account as these are needed during setup of this Home Assistant integration.
- In DConnect, add your installation via the device serial number.

### DConnect Account
The DAB Pumps DConnect website and app seem to have a problem with multiple logins from the same account. I.e. when already logged into the app or website, then a subsequent login via this library may fail. 

Therefore it is recommended to create a separate account within DAB Pumps DConnect that is specific for script use. 
- Create a fresh email address specifically for scripting at gmail, outlook or another provider. 
- Register this email address in the DAB Pumps DConnect website. Go to  [internetofpumps.com](https://internetofpumps.com/). Select 'Professional Users' and 'Open DConnect', or one of the apps.
- When entering your details and needing to choose between 'Professional' or 'End User' either are good, this has no implications on the website, app or this library.
- Then, while logged in into DAB Pumps DConnect using your normal account, go to 'installation settings' and under 'manage permissions' press 'Add member' to invite the newly created email account. Access level 'Installer' is recommended to be able to use all features of the library.


# Usage

The library is available from PyPi using:
`pip install aiodabpumps`

See example_api_use.py for an example of usage.
