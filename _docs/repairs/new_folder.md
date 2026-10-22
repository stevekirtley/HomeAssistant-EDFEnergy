# Repairs - EDF Energy has a new folder

From version 21 this integration installs into `custom_components/edfenergy_uk` instead of
`custom_components/edf_energy`. HACS adds the new folder but leaves the old one in place, so
for a while both are on your system and there is one step to finish by hand.

Nothing is broken in the meantime. Until you complete the step below, the old folder carries
on running your account exactly as before.

## Finishing the move

1. Go to **Settings > Devices & services** and press **Add integration**.
2. Choose **EDF Energy (UK)**. Both are listed while the old folder is still there, and
   this is the new one.
3. It will tell you it has found your existing setup and ask to take it over. Confirm.

Your account, your API key, every entity id and your history all carry across, so
automations, scripts, dashboards and template sensors keep working untouched. Energy
dashboard statistics, including cost history, come with it.

## Afterwards

Delete `custom_components/edf_energy` and restart Home Assistant.

If you leave it there nothing stops working, but the folder is doing nothing and Home
Assistant will keep listing it.

## If "EDF Energy (UK)" is not in the Add integration list

Restart Home Assistant and try again. The new folder is only picked up on a restart after
HACS has downloaded it.

## If you pick the wrong one

Nothing happens. The old **EDF Energy** stops short and tells you to use **EDF Energy (UK)**,
so there is no way to end up with your account set up twice.
