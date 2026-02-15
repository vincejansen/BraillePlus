#Braille improvement add-on for NVDA. 
#This add-on is released under GPL version 2. 
#Copyright 2025 Vince Jansen <jansen.vince@gmail.com> 
#Attribra is copyright 2017 Alberto Zanella <lapostadialberto@gmail.com>
  
import braille
import api
import config
import controlTypes
import globalPluginHandler
from scriptHandler import script
import ui
import languageHandler
from config.configFlags import TetherTo, BrailleMode

from gui.settingsDialogs import BrailleSettingsPanel
from gui import guiHelper
import wx

try:
    _  # noqa: B018
except NameError:
    def _(s):
        return s

def _isDutchUI():
    """Return True if NVDA's interface language is Dutch (nl*)."""
    try:
        lang = languageHandler.getLanguage() or ""
    except Exception:
        lang = ""
    return lang.lower().startswith("nl")

def _L(nlText: str, enText: str) -> str:
    """Return Dutch text when NVDA is set to Dutch, otherwise English."""
    return nlText if _isDutchUI() else enText

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
    ui.message(
        _L("Selectiemarkering in braille: ingeschakeld", "Selection marking in braille: enabled")
        if enabled else
        _L("Selectiemarkering in braille: uitgeschakeld", "Selection marking in braille: disabled")
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
                label=_L("Markeer geselecteerde items met punten 7 en 8 (alleen itemtekst)", "Mark selected items with dots 7 and 8 (item text only)")
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

    def terminate(self):
        try:
            braille.pre_writeCells.unregister(self._onPreWriteCells)
        except Exception:
            pass
        _unpatchBrailleSettingsPanel()
        super().terminate()

    @script(
        description=_L("Schakelt selectiemarkering met punten 7 en 8 in braille aan of uit.", "Toggles selection marking with dots 7 and 8 in braille."),
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
