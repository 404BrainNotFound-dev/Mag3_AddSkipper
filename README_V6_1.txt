mag3_addskipper V6.1

Purpose

mag3_addskipper is a local screen automation tool for testing apps on visible virtual Android screens.

This version does not use ADB.
This version does not edit the tested app.
This version works by watching the laptop screen and clicking selected screen areas.

Main V6.1 Changes

1. More precise close button clicks

The close template crop size is now smaller by default.
The close button crop size is 36 pixels.
The back button crop size is 44 pixels.

This makes the selected X or close button tighter and helps the click land closer to the real button center.

2. Each screen is checked for 3 seconds

Automation now checks one enabled screen for a full 3 seconds before moving to the next screen.

Example

Screen 1 is checked for 3 seconds
Screen 2 is checked for 3 seconds
Screen 3 is checked for 3 seconds
Then the loop starts again from Screen 1

During those 3 seconds the tool keeps searching for close X or skip templates.

3. App icon start check

When Start is clicked the selected app profile is loaded.

The tool checks every enabled phone screen for the selected app icon first.

If the app icon is visible it clicks it.

If the app icon is not visible it continues normal automation.

4. Shared templates for all screens in the selected app

The selected app profile has one set of templates.

The same close templates are searched on every enabled screen.

The tool does not require separate close templates for each screen.

5. Sequential screen search

The tool searches screen 1 first.
If no match is found it moves to screen 2.
Then it moves to screen 3.
This continues until the last enabled screen.
Then it starts again from screen 1.

Startup

Use this file for normal use

START_GUI_NO_CMD.vbs

Use this file only to see errors

START_GUI_DEBUG.bat

Basic Setup

1. Open LDCloud.
2. Make all mobile screens visible.
3. Open START_GUI_NO_CMD.vbs.
4. Select or create the app profile.
5. Open Settings.
6. Select Mobile Screens.
7. Select Detection Zones.
8. Add Close By Cross.
9. Add App Icon By Cross if you want app launch detection.
10. Add Back By Cross if you want recovery.
11. Go to Home.
12. Click Start.

Important Settings

Template trust

This controls how strong the image match must be.

Seconds per screen

Default is 3.
This controls how long each screen is checked before moving to the next screen.

Scan delay

Default is 0.01.
Lower value scans faster.

Close crop size

Default is 36.
Smaller crop makes the close button template tighter.

Back crop size

Default is 44.

App icon crop size

Default is 96.

Daily Use

1. Open LDCloud screens.
2. Open mag3_addskipper.
3. Select the app profile.
4. Click Start.
5. The tool checks app icons first.
6. The tool then searches each screen for close templates for 3 seconds.
7. Click Stop when finished.

Backup

Important data is inside

DATA_BACKUP_COPY_ME

Copy this folder to backup your setup.

End
