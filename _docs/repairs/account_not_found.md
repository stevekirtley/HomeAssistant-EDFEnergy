# Repairs - Account not found

If you receive the fixable warning around your account information not being found, there are two possible causes and solutions

## API Key is invalid

The simplest cause is that your API key has become invalid. This can happen if you have recently reset your API key in your [EDF Energy dashboard](https://www.edfenergy.com/for-home/myaccount).

To fix
1. Navigate to [EDF Energy integrations](https://my.home-assistant.io/redirect/integration/?domain=edf_energy)
2. Find the entry marked with your account id (e.g. `A-AAAA1111`) and click on 'Configure'
1. Update your API key with your new one displayed on your [EDF Energy dashboard](https://www.edfenergy.com/for-home/myaccount).
2. Click 'Submit'

## Account id is invalid

If you have setup the integration with an account that is no longer valid, you will need to manually remove all entries for the integration.

To fix
1. Navigate to [EDF Energy integrations](https://my.home-assistant.io/redirect/integration/?domain=edf_energy)
2. For each entry, click on the three dots and then click on 'Delete'

Once done, you can then add the integration fresh with your new account.