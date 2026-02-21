# -*- coding: utf-8 -*-
#Braille improvement add-on for NVDA. 
#This add-on is released under GPL version 2. 
#Copyright 2025 Vince Jansen <jansen.vince@gmail.com> 
#Attribra is copyright 2017 Alberto Zanella <lapostadialberto@gmail.com>
  
import addonHandler
addonHandler.initTranslation()

# Logboek (NVDA log)
try:
    from logHandler import log
except Exception:  # Fallback for unit tests / non-NVDA environments
    import logging
    log = logging.getLogger(__name__)


def _logAddonLoaded():
    """Write a friendly info line to the NVDA log when the add-on loads."""
    try:
        addon = addonHandler.getCodeAddon()
        if addon and getattr(addon, "manifest", None):
            name = addon.manifest.get("name") or addon.name or "Add-on"
            version = addon.manifest.get("version") or ""
            if version:
                log.info(f"{name} {version} loaded")
            else:
                log.info(f"{name} loaded")
        else:
            log.info("BrailleSelection add-on loaded")
    except Exception:
        log.info("BrailleSelection add-on loaded")


import braille
import api
import config
import controlTypes
import globalPluginHandler
from scriptHandler import script
import ui
from config.configFlags import TetherTo, BrailleMode

from gui.settingsDialogs import BrailleSettingsPanel
from gui import guiHelper
import wx

try:
    _  # noqa: B018
except NameError:
    def _(s):
        return s

# ----------------
# Config
# ----------------
CONF_SECTION = "selectedDots"

if CONF_SECTION not in config.conf.spec:
    config.conf.spec[CONF_SECTION] = {}
# default True
config.conf.spec[CONF_SECTION]["enabled"] = "boolean(default=True)"

def _isEnabled():
    return bool(config.conf[CONF_SECTION].get("enabled", True))

def _setEnabled(value):
    config.conf[CONF_SECTION]["enabled"] = bool(value)

def _announceEnabledState(enabled):
        # Translators: Message reported when braille selection marking has been enabled.
    # Translators: This is spoken/brailled immediately after toggling the feature.
    ui.message(
        _("Braille selection marking: enabled")
        if enabled else
        # Translators: Message reported when braille selection marking has been disabled.
        _("Braille selection marking: disabled")
    )

SELECTION_SHAPE = 0xC0  # dots 7+8

# -----------------------------
# Patch Braille settings panel
# -----------------------------
_originalMakeSettings = None
_originalOnSave = None

def _patchBrailleSettingsPanel():
    global _originalMakeSettings, _originalOnSave

    if _originalMakeSettings is not None:
        return

    _originalMakeSettings = BrailleSettingsPanel.makeSettings
    _originalOnSave = BrailleSettingsPanel.onSave

    def makeSettingsPatched(self, settingsSizer):
        _originalMakeSettings(self, settingsSizer)

        helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self._selectedDotsEnableChk = helper.addItem(
            wx.CheckBox(
                self,
                # Translators: Label for a checkbox in NVDA's Braille settings panel.
# Translators: When enabled, dots 7 and 8 are added to the braille cells corresponding to the selected item's text.
                label=_("Mark selected items with dots 7 and 8 (item text only)")
            )
        )
        self._selectedDotsEnableChk.SetValue(_isEnabled())

    def onSavePatched(self):
        _originalOnSave(self)
        if hasattr(self, "_selectedDotsEnableChk"):
            _setEnabled(self._selectedDotsEnableChk.GetValue())

    BrailleSettingsPanel.makeSettings = makeSettingsPatched
    BrailleSettingsPanel.onSave = onSavePatched

def _unpatchBrailleSettingsPanel():
    global _originalMakeSettings, _originalOnSave
    if _originalMakeSettings is None:
        return

    BrailleSettingsPanel.makeSettings = _originalMakeSettings
    BrailleSettingsPanel.onSave = _originalOnSave
    _originalMakeSettings = None
    _originalOnSave = None

# ----------------
# Global plugin
# ----------------
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        _patchBrailleSettingsPanel()
        braille.pre_writeCells.register(self._onPreWriteCells)
        _logAddonLoaded()

    def terminate(self):
        try:
            braille.pre_writeCells.unregister(self._onPreWriteCells)
        except Exception:
            pass
        _unpatchBrailleSettingsPanel()
        super().terminate()

    @script(
        # Translators: Description for an input gesture/script.
# Translators: This script toggles marking of selected items in braille using dots 7 and 8.
        description=_("Toggles braille selection marking with dots 7 and 8 on or off."),
        # Translators: Script category in the Input Gestures dialog.
        category=_("Braille")
    )
    def script_toggleSelectedDots(self, gesture):
        newVal = not _isEnabled()
        _setEnabled(newVal)
        _announceEnabledState(newVal)

    def _onPreWriteCells(self, cells, rawText, currentCellCount):
        if not _isEnabled():
            return


        if config.conf["braille"]["mode"] != BrailleMode.FOLLOW_CURSORS.value:
            return
        if braille.handler.getTether() != TetherTo.FOCUS.value:
            return
        if braille.handler.buffer is not braille.handler.mainBuffer:
            return

        focusObj = api.getFocusObject()
        if not focusObj or controlTypes.State.SELECTED not in focusObj.states:
            return

        buf = braille.handler.mainBuffer

        # 1) Vind de region die bij het focus-object hoort
        targetRegion = None
        targetRegionStart = None
        for region, start, end in buf.regionsWithPositions:
            if getattr(region, "obj", None) is focusObj:
                targetRegion = region
                targetRegionStart = start
                break
        if not targetRegion:
            return

        # 2) Itemtekst
        name = (focusObj.name or "").strip()
        if not name:
            return

        raw = targetRegion.rawText or ""
        rawStart = raw.find(name)
        if rawStart < 0:
            return
        rawEnd = rawStart + len(name)

        # 3) raw -> braille mapping
        r2b = targetRegion.rawToBraillePos
        if not r2b or (rawEnd - 1) >= len(r2b):
            return

        brailleStartInRegion = r2b[rawStart]
        brailleEndInRegion = r2b[rawEnd - 1] + 1  # exclusief

        # 4) Regionposities -> windowposities
        bufferStart = targetRegionStart + brailleStartInRegion
        bufferEnd = targetRegionStart + brailleEndInRegion

        for bufferPos in range(bufferStart, bufferEnd):
            try:
                windowPos = buf.bufferPosToWindowPos(bufferPos)
            except LookupError:
                continue
            if 0 <= windowPos < len(cells):
                cells[windowPos] |= SELECTION_SHAPE
