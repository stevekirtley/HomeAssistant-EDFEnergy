# Updating To Version 21

Version 21 installs into a new folder, `custom_components/edfenergy_uk`, and is listed as
**EDF Energy (UK)** instead of **EDF Energy**. Everything the integration does is unchanged.

HACS downloads the new folder but leaves the old one in place, and Home Assistant will not
start using the new folder on its own. There is one step to finish by hand, and what you see
on screen depends entirely on which version you are updating **from**.

Nothing is lost at any point. Your account, your API key, every entity id, your history and
your Energy dashboard statistics all come across, so automations, scripts, dashboards and
template sensors carry on untouched.

## First, check which version you are on

In HACS, open **EDF Energy**. The version you have installed is shown at the top of the page.

| You are on | What happens when you update | What you need to do |
|---|---|---|
| **20.1.1** | The integration keeps running and puts a notice in **Repairs** | One click. [Go to Path A](#path-a-updating-from-2011) |
| **20.1.0** | The integration stops loading and every entity goes unavailable | Update to 20.1.1 **first**. [Go to Path B](#path-b-updating-from-2010) |
| **20.0.0 or any 19.x** | Nothing changes and nothing prompts you | Start the move yourself. [Go to Path C](#path-c-updating-from-2000-or-any-19x) |

!!! tip "The short version"

    Whatever you are on, updating to **20.1.1** and restarting before you take version 21 gives
    you the easiest path. From 20.1.1 the integration walks you through the rest.

---

## Path A: updating from 20.1.1

This is the guided path. After HACS downloads version 21 and you restart, the old folder
carries on running your account exactly as before — nothing goes unavailable — and a notice
appears in **Settings > System > Repairs**:

![The repair notice saying EDF Energy has a new folder](../assets/v21-repairs-notice.png)

Click it, and you get this:

![The Finish the move dialog, with a Hand it over button](../assets/v21-finish-the-move.png)

Press **Hand it over**. That is the whole move — there is nothing to fill in and nothing to
reconfigure. Your account is now running from the new folder.

Then follow [Afterwards](#afterwards-deleting-the-old-folder) to clear out the old folder.

!!! info "If the notice does not appear"

    Restart Home Assistant. A folder HACS has only just downloaded is not picked up until a
    restart, and the notice is raised when the integration next starts.

---

## Path B: updating from 20.1.0

!!! warning "Update to 20.1.1 first"

    Going straight from 20.1.0 to version 21 stops the integration loading. Every entity goes
    unavailable and stays that way until you finish the move by hand.

    In HACS, update to **20.1.1**, restart Home Assistant, and then take version 21. You will
    then be on [Path A](#path-a-updating-from-2011) and get the one-click prompt.

### If you have already updated

Your EDF Energy entry in **Settings > Devices & services** will be showing an error, and the
log will have:

```
Replaced by edfenergy_uk. Delete custom_components/edf_energy and restart.
```

There is also a notice in Repairs titled **EDF Energy has moved to a new folder**.

!!! danger "Do not follow that advice"

    Both that message and that notice tell you to delete `custom_components/edf_energy` and
    restart. **That does not fix it**, and if you do it first you are left with your account
    attached to a folder that is no longer there, with nothing on screen explaining why.

    This was wrong in 20.1.0 and is corrected from 20.1.1 onwards. Use the steps below instead.

To recover, hand the account over from the new integration's own setup screen. These are the
same steps as [Path C](#path-c-updating-from-2000-or-any-19x) below.

1. Go to **Settings > Devices & services** and press **Add integration**.
2. Search for `EDF`. While both folders are installed you will see an entry for each, and the
   name is what tells them apart — the new one has **(UK)** on the end.

    ![The Add integration list showing EDF Energy and EDF Energy (UK)](../assets/v21-add-integration-both.png)

3. Choose **EDF Energy (UK)**. It finds the setup the old folder is holding and offers to take
   it over:

    ![The Take over your existing EDF Energy setup dialog, with a Take it over button](../assets/v21-take-over.png)

4. Press **Take it over**. You get a confirmation that the move is done, and your entities come
   back:

    ![Confirmation that the setup has been moved to the new folder](../assets/v21-taken-over.png)

This works whether or not you have already deleted the old folder, so if you followed the wrong
advice before reading this, the same steps still put you right.

Then follow [Afterwards](#afterwards-deleting-the-old-folder).

---

## Path C: updating from 20.0.0 or any 19.x

!!! warning "Nothing will prompt you"

    These versions know nothing about the new folder. After you update, **the old folder simply
    carries on working** — every entity stays available and nothing appears in Repairs — while
    the new folder sits on disk doing nothing.

    It looks like the update worked. It downloaded, but none of version 21 is running, and it
    will stay that way until you do the step below. HACS will show version 21 as installed, so
    nothing further will remind you.

The tidiest route is to update to **20.1.1** first and restart, which puts you on
[Path A](#path-a-updating-from-2011) and does the rest for you.

If you are already on version 21, start the move yourself using the **Add integration** steps
shown in [Path B](#if-you-have-already-updated) above — search for `EDF`, choose
**EDF Energy (UK)**, and press **Take it over**.

Then follow [Afterwards](#afterwards-deleting-the-old-folder).

---

## Afterwards: deleting the old folder

Once your account has moved, the notice from the old folder goes and a new one takes its place:

![The repair notice saying the old EDF Energy folder can be deleted](../assets/v21-delete-old-folder.png)

Press **Delete it**, then restart Home Assistant. Until you restart, Home Assistant carries on
listing the copy it had already loaded — that is expected and harmless.

If you would rather do it yourself, delete the `custom_components/edf_energy` folder and restart.
Leaving it in place does not break anything, but Home Assistant will keep listing it and the
notice will keep coming back.

## What carries over

| | Comes across |
|---|---|
| Account number and API key | Yes |
| Every entity id | Yes, unchanged |
| Entity history | Yes |
| Energy dashboard statistics, including cost history | Yes |
| Automations, scripts, dashboards, template sensors | Keep working untouched |
| Cost tracker and tariff comparison sensors | Yes |

You do not need to re-enter your credentials, and you do not need to edit anything that refers
to an EDF Energy entity.

## Questions

### Will my automations break?

No. Entity ids are preserved exactly, so anything that refers to them carries on working.

### Do I need my password again?

No. Your stored API key moves across with the account.

### Why has it moved at all?

The folder name and the listed name both needed to change for the integration to be distinct
within HACS. The rename is the whole of it — no features have been removed.

### Can I just delete the old folder and let the new one pick things up?

No. Home Assistant only starts an integration that something already refers to, and until the
hand-over has happened nothing refers to the new folder. Deleting the old folder first leaves
your account attached to nothing. Always hand it over first, then delete.

### I pressed the old EDF Energy in the Add integration list by mistake

From 20.1.1 that is harmless — the old one stops short and points you at **EDF Energy (UK)**.
Nothing can end up set up twice.

### Where do I get help?

See the [new folder repair notes](../repairs/new_folder.md), the [FAQ](../faq.md), or raise a
[discussion](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/discussions).
