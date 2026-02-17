#AttriBra Addon for NVDA
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2017 Alberto Zanella <lapostadialberto@gmail.com>
#
# Extended with an NVDA Settings panel (Attribra) to edit attribra.ini without manual editing.

import os
import globalVars
import globalPluginHandler
import appModuleHandler
import braille
import api
import ui
from logHandler import log
from configobj import ConfigObj  # INI file parsing

# NVDA GUI imports (optional in secure/silent contexts)
import wx
import gui
from gui import guiHelper
from gui import settingsDialogs

import addonHandler
addonHandler.initTranslation()
from addonHandler import getCodeAddon  # type: ignore

ATTRS = {}
logTextInfo = False


def _parse_value_to_list(value):
	"""Convert ini value to a list used for comparisons.
	Attribra expects a boolean-like value: 0 (uit) of 1 (aan).
	We keep both the string and int representations so it matches NVDA's field values
	(which may be bools/ints).
	"""
	if isinstance(value, (list, tuple)):
		# Take the first item if a list was stored.
		value = value[0] if value else ""
	if value is None:
		value = ""
	v = str(value).strip()
	if v in ("0", "1"):
		i = int(v)
		# bool(i) compares equal to i, but including int is enough; keep both for clarity.
		return [v, i]
	# Any unexpected value is kept as-is (it simply won't match boolean fields).
	return [v]


def _list_to_ini_value(values):
	"""Convert the internal list back to a single ini string for storage.
	We store a single '0' or '1'.
	"""
	if not values:
		return ""
	# Prefer an int/bool if present.
	for v in values:
		if isinstance(v, bool):
			return "1" if v else "0"
		if isinstance(v, int) and v in (0, 1):
			return str(v)
	# Fallback to string.
	v0 = str(values[0]).strip()
	if v0 in ("0", "1"):
		return v0
	return v0


def decorator(fn, which):
	def _getTypeformFromFormatField(self, field, formatConfig):
		# convention: to mark we put 4 (bold for liblouis)
		for attr, value in ATTRS.items():
			fval = field.get(attr, False)
			if fval in value:
				return 4
		return 0

	def addTextWithFields_edit(self, info, formatConfig, isSelection=False):
		conf = formatConfig.copy()
		conf["reportFontAttributes"] = True
		conf["reportColor"] = True
		conf["reportSpellingErrors"] = True
		if logTextInfo:
			log.info(info.getTextWithFields(conf))
		fn(self, info, conf, isSelection)

	def update(self):
		fn(self)
		DOT7 = 64
		DOT8 = 128
		for i in range(0, len(self.rawTextTypeforms)):
			if self.rawTextTypeforms[i] == 4:
				self.brailleCells[i] |= DOT7 | DOT8

	if which == "addTextWithFields":
		return addTextWithFields_edit
	if which == "update":
		return update
	if which == "_getTypeformFromFormatField":
		return _getTypeformFromFormatField


class AttribraRuleDialog(wx.Dialog):
	"""Dialog to add/edit one rule: attribute + values."""

	def __init__(self, parent, title, attrName="", valuesText=""):
		super().__init__(parent, title=title)
		self.attrName = attrName
		self.valuesText = valuesText

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

		self.attrCtrl = sHelper.addLabeledControl(_("Attribuutnaam"), wx.TextCtrl)
		self.attrCtrl.SetValue(attrName)

		self.valCtrl = sHelper.addLabeledControl(
			_("Waarde (0 = uit, 1 = aan)"),
			wx.Choice,
			choices=["0", "1"],
		)
		# Normalize existing value to 0/1
		v = (valuesText or "").strip()
		if "," in v:
			v = v.split(",", 1)[0].strip()
		if v not in ("0", "1"):
			v = "0"
		self.valCtrl.SetSelection(0 if v == "0" else 1)

		mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND)

		btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(btns, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND)

		self.SetSizerAndFit(mainSizer)

	def getData(self):
		return self.attrCtrl.GetValue().strip(), self.valCtrl.GetStringSelection().strip()


class AttribraSettingsPanel(settingsDialogs.SettingsPanel):
	title = _("Attribra")

	def makeSettings(self, settingsSizer):
		self.plugin = getattr(self, "_attribraPlugin", None)

		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		self.sectionChoice = sHelper.addLabeledControl(_("Sectie / Applicatie"), wx.Choice)
		self.sectionChoice.Bind(wx.EVT_CHOICE, self._onSectionChanged)

		# Section (application) management buttons
		sectionBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.addSectionBtn = wx.Button(self, label=_("Applicatie toevoegen…"))
		self.delSectionBtn = wx.Button(self, label=_("Applicatie verwijderen"))
		self.addSectionBtn.Bind(wx.EVT_BUTTON, self._onAddSection)
		self.delSectionBtn.Bind(wx.EVT_BUTTON, self._onDeleteSection)
		sectionBtnSizer.Add(self.addSectionBtn, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sectionBtnSizer.Add(self.delSectionBtn, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sHelper.addItem(sectionBtnSizer)

		self.rulesList = sHelper.addLabeledControl(_("Regels"), wx.ListBox)
		self.rulesList.Bind(wx.EVT_LISTBOX_DCLICK, self._onEdit)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.addBtn = wx.Button(self, label=_("Toevoegen…"))
		self.editBtn = wx.Button(self, label=_("Bewerken…"))
		self.delBtn = wx.Button(self, label=_("Verwijderen"))
		self.reloadBtn = wx.Button(self, label=_("Herladen"))

		self.addBtn.Bind(wx.EVT_BUTTON, self._onAdd)
		self.editBtn.Bind(wx.EVT_BUTTON, self._onEdit)
		self.delBtn.Bind(wx.EVT_BUTTON, self._onDelete)
		self.reloadBtn.Bind(wx.EVT_BUTTON, self._onReload)

		for b in (self.addBtn, self.editBtn, self.delBtn, self.reloadBtn):
			btnSizer.Add(b, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)

		sHelper.addItem(btnSizer)

		self._refreshSections()

	def _normalizeSectionName(self, name: str) -> str:
		# Keep it simple: strip whitespace.
		# App names in NVDA are typically executable base names (e.g. 'winword').
		return (name or "").strip()

	def _selectSectionByName(self, name: str):
		items = list(self.sectionChoice.GetItems())
		try:
			idx = items.index(name)
		except ValueError:
			return
		self.sectionChoice.SetSelection(idx)
		self._refreshRules()

	def _refreshSections(self):
		if not self.plugin:
			self.sectionChoice.SetItems(["global"])
			self.sectionChoice.SetSelection(0)
			self._refreshRules()
			return

		sections = sorted(set(self.plugin.configs.keys()) | {"global"})
		self.sectionChoice.SetItems(sections)
		# keep selection if possible
		if self.sectionChoice.GetSelection() == wx.NOT_FOUND:
			self.sectionChoice.SetSelection(0)
		self._refreshRules()

	def _onAddSection(self, evt):
		if not self.plugin:
			return
		dlg = wx.TextEntryDialog(
			self,
			_("Geef de naam van de applicatie/sectie op (bijv. 'winword' of 'firefox')."),
			_("Applicatie toevoegen"),
			"",
		)
		if dlg.ShowModal() == wx.ID_OK:
			name = self._normalizeSectionName(dlg.GetValue())
			if not name:
				ui.message(_("Naam ontbreekt."))
				dlg.Destroy()
				return
			# If a case-insensitive match exists, reuse it.
			existing = None
			for s in self.plugin.configs.keys():
				if s.lower() == name.lower():
					existing = s
					break
			if existing is None:
				self.plugin.configs.setdefault(name, {})
				self._refreshSections()
				self._selectSectionByName(name)
			else:
				self._refreshSections()
				self._selectSectionByName(existing)
				ui.message(_("Deze applicatie bestaat al."))
		dlg.Destroy()

	def _onDeleteSection(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		# 'global' is always shown; deleting it clears/removes stored rules.
		if section not in self.plugin.configs and section != "global":
			return
		msg = _("Weet je zeker dat je de applicatie/sectie '{name}' wilt verwijderen? Alle regels in deze sectie worden verwijderd.").format(
			name=section
		)
		res = wx.MessageBox(msg, _("Bevestigen"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
		if res != wx.YES:
			return
		self.plugin.configs.pop(section, None)
		self._refreshSections()
		self._selectSectionByName("global")
		ui.message(_("Applicatie verwijderd."))

	def _currentSection(self):
		i = self.sectionChoice.GetSelection()
		if i == wx.NOT_FOUND:
			return "global"
		return self.sectionChoice.GetString(i)

	def _refreshRules(self):
		section = self._currentSection()
		mapping = (self.plugin.configs.get(section) if self.plugin else None) or {}
		items = []
		for attr, vals in sorted(mapping.items(), key=lambda x: x[0].lower()):
			items.append(f"{attr} = {_list_to_ini_value(vals)}")
		self.rulesList.SetItems(items)
		if items:
			self.rulesList.SetSelection(0)

	def _onSectionChanged(self, evt):
		self._refreshRules()

	def _selectedAttr(self):
		section = self._currentSection()
		mapping = (self.plugin.configs.get(section) if self.plugin else None) or {}
		sel = self.rulesList.GetSelection()
		if sel == wx.NOT_FOUND:
			return None, None
		line = self.rulesList.GetString(sel)
		if "=" not in line:
			return None, None
		attr = line.split("=", 1)[0].strip()
		return attr, mapping.get(attr)

	def _ensureSectionExists(self, section):
		if section not in self.plugin.configs:
			self.plugin.configs[section] = {}

	def _onAdd(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		self._ensureSectionExists(section)

		dlg = AttribraRuleDialog(self, _("Regel toevoegen"))
		if dlg.ShowModal() == wx.ID_OK:
			attr, valsText = dlg.getData()
			if not attr:
				ui.message(_("Attribuutnaam ontbreekt."))
				return
			self.plugin.configs[section][attr] = _parse_value_to_list(valsText)
			self._refreshRules()
		dlg.Destroy()

	def _onEdit(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		attr, vals = self._selectedAttr()
		if not attr:
			return
		currentText = _list_to_ini_value(vals or [])
		dlg = AttribraRuleDialog(self, _("Regel bewerken"), attrName=attr, valuesText=currentText)
		if dlg.ShowModal() == wx.ID_OK:
			newAttr, valsText = dlg.getData()
			if not newAttr:
				ui.message(_("Attribuutnaam ontbreekt."))
				return
			# rename if needed
			if newAttr != attr:
				self.plugin.configs[section].pop(attr, None)
			self.plugin.configs[section][newAttr] = _parse_value_to_list(valsText)
			self._refreshRules()
		dlg.Destroy()

	def _onDelete(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		attr, _vals = self._selectedAttr()
		if not attr:
			return
		self.plugin.configs.get(section, {}).pop(attr, None)
		self._refreshRules()

	def _onReload(self, evt):
		if not self.plugin:
			return
		self.plugin.parsecfgs()
		self._refreshSections()
		ui.message(_("Attribra-instellingen herladen."))

	def onSave(self):
		if not self.plugin:
			return
		try:
			self.plugin.savecfgs()
			# refresh active rules for current focus app
			try:
				obj = api.getFocusObject()
				if obj:
					self.plugin.populateAttrs(obj.processID)
			except Exception:
				pass
			ui.message(_("Attribra-instellingen opgeslagen."))
		except Exception:
			log.exception("Error saving Attribra settings")
			ui.message(_("Opslaan mislukt; zie log voor details."))


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	configs = {}
	currentPid = ""

	def __init__(self):
		self.configFile = os.path.join(globalVars.appArgs.configPath, "addons", "BraillePlus", "attribra.ini")
		self.parsecfgs()  # parse configuration

		if len(self.configs) > 0:  # If no cfg then do not replace functions
			braille.TextInfoRegion._addTextWithFields = decorator(
				braille.TextInfoRegion._addTextWithFields, "addTextWithFields"
			)
			braille.TextInfoRegion.update = decorator(braille.TextInfoRegion.update, "update")
			braille.TextInfoRegion._getTypeformFromFormatField = decorator(
				braille.TextInfoRegion._getTypeformFromFormatField, "_getTypeformFromFormatField"
			)

		# Register settings panel under a dedicated category.
		try:
			AttribraSettingsPanel._attribraPlugin = self
			if AttribraSettingsPanel not in settingsDialogs.NVDASettingsDialog.categoryClasses:
				settingsDialogs.NVDASettingsDialog.categoryClasses.append(AttribraSettingsPanel)
		except Exception:
			log.exception("Could not register Attribra settings panel")

		super(GlobalPlugin, self).__init__()

	def terminate(self):
		# Unregister settings panel
		try:
			if AttribraSettingsPanel in settingsDialogs.NVDASettingsDialog.categoryClasses:
				settingsDialogs.NVDASettingsDialog.categoryClasses.remove(AttribraSettingsPanel)
		except Exception:
			pass
		super(GlobalPlugin, self).terminate()

	def event_gainFocus(self, obj, nextHandler):
		nextHandler()
		pid = obj.processID
		if self.currentPid != pid:
			self.populateAttrs(pid)
			self.currentPid = pid

	def populateAttrs(self, pid):
		if len(self.configs) == 0:
			return
		global ATTRS  # We are changing the global variable
		appname = appModuleHandler.getAppNameFromProcessID(pid)
		if appname in self.configs:
			ATTRS = self.configs[appname]
		elif "global" in self.configs:
			ATTRS = self.configs["global"]
		else:
			ATTRS = {}

	def parsecfgs(self):
		self.configs = {}
		try:
			config = ConfigObj(self.configFile, encoding="UTF-8")
			for app, mapping in config.items():
				mappings = {}
				for name, value in mapping.items():
					mappings[name] = _parse_value_to_list(value)
				self.configs[app] = mappings
		except IOError:
			log.debugWarning("No attribra.ini found")
		except Exception:
			log.exception("Error reading attribra.ini")

	def savecfgs(self):
		# Write current configs to attribra.ini
		cfg = ConfigObj(encoding="UTF-8")
		cfg.filename = self.configFile
		for section, mapping in self.configs.items():
			cfg.setdefault(section, {})
			for attr, vals in mapping.items():
				cfg[section][attr] = _list_to_ini_value(vals)
		# Ensure directory exists
		os.makedirs(os.path.dirname(self.configFile), exist_ok=True)
		cfg.write()
		# Reparse so internal types are normalized (ints, RGB parsing, etc.)
		self.parsecfgs()

	# Legacy gesture: open settings instead of opening ini directly.
	def script_editConfig(self, gesture):
		try:
			gui.mainFrame.onNVDASettingsCommand(None)
		except Exception:
			# fallback to opening the ini file if settings dialog can't be opened
			try:
				self.parsecfgs()
				os.system("start " + self.configFile)
			except Exception:
				log.exception("Could not open settings or ini file")

	def script_logFieldsAtCursor(self, gesture):
		global logTextInfo
		logTextInfo = not logTextInfo
		msg = ["stop", "start"]
		ui.message(_("debug textInfo ") + msg[int(logTextInfo)])

	__gestures = {
		"kb:NVDA+control+a": "editConfig",
		"kb:NVDA+control+shift+a": "logFieldsAtCursor",
	}
