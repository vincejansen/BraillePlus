# -*- coding: utf-8 -*-

#AttriBra Addon for NVDA
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2017 Alberto Zanella <lapostadialberto@gmail.com>
#
# Extended with an NVDA Settings panel (Attribra) to edit attribra.ini without manual editing.
#Copyright 2025 Vince Jansen <jansen.vince@gmail.com>
import os

import addonHandler
addonHandler.initTranslation()
from addonHandler import getCodeAddon  # type: ignore

import api
import appModuleHandler
import braille
import globalPluginHandler
import globalVars
import ui
from logHandler import log

from configobj import ConfigObj  # INI file parsing

# NVDA GUI imports
import gui
from gui import guiHelper, settingsDialogs
import wx

ATTRS = {}
logTextInfo = False

# Internal marker bit used in rawTextTypeforms. This should not clash with liblouis constants.
ATTRIBRA_TYPEFORM_MARKER = 1 << 20


def _parse_value_to_list(value):
	"""Convert INI value to a list used for comparisons.

	Attribra expects a boolean-like value: 0 (off) or 1 (on).
	NVDA format fields typically use booleans for many attributes (e.g. bold=True).
	Therefore we store multiple equivalent representations so matching is robust.
	"""
	if isinstance(value, (list, tuple)):
		# Take the first item if a list was stored.
		value = value[0] if value else ""
	if value is None:
		value = ""
	v = str(value).strip()
	if v in ("0", "1"):
		i = int(v)
		b = bool(i)
		# Include string, int and bool representations.
		return [v, i, b]
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
		# Start with NVDA's default typeform calculation.
		base = fn(self, field, formatConfig)
		# If any configured attribute matches, set our marker bit.
		for attr, value in ATTRS.items():
			fval = field.get(attr, False)
			if fval in value:
				return base | ATTRIBRA_TYPEFORM_MARKER
		return base

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
		# rawTextTypeforms entries can contain multiple liblouis flags ORed together.
		# We use a dedicated marker bit to decide where dots 7 and 8 should be applied.
		for i in range(0, len(self.rawTextTypeforms)):
			try:
				tf = self.rawTextTypeforms[i]
			except Exception:
				continue
			if tf & ATTRIBRA_TYPEFORM_MARKER:
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

		# Translators: Label for the text field where the user enters the name of a formatting attribute.
		self.attrCtrl = sHelper.addLabeledControl(_("Attribute name"), wx.TextCtrl)
		self.attrCtrl.SetValue(attrName)

		# Translators: Label for the choice field that sets a rule value (0 = off, 1 = on).
		self.valCtrl = sHelper.addLabeledControl(
			_("Value (0 = off, 1 = on)"),
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
	# Translators: Title of the add-on settings panel shown in NVDA Settings.
	title = _("Attribra")

	def makeSettings(self, settingsSizer):
		self.plugin = getattr(self, "_attribraPlugin", None)

		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# Translators: Label for the list of available sections (applications) in the Attribra settings.
		self.sectionChoice = sHelper.addLabeledControl(_("Section / Application"), wx.Choice)
		self.sectionChoice.Bind(wx.EVT_CHOICE, self._onSectionChanged)

		# Section (application) management buttons
		sectionBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button label in Attribra settings to add an application-specific section.
		self.addSectionBtn = wx.Button(self, label=_("Add application…"))
		# Translators: Button label in Attribra settings to delete an application-specific section.
		self.delSectionBtn = wx.Button(self, label=_("Delete application"))
		self.addSectionBtn.Bind(wx.EVT_BUTTON, self._onAddSection)
		self.delSectionBtn.Bind(wx.EVT_BUTTON, self._onDeleteSection)
		sectionBtnSizer.Add(self.addSectionBtn, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sectionBtnSizer.Add(self.delSectionBtn, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sHelper.addItem(sectionBtnSizer)

		# Translators: Label for the list of rules in the Attribra settings.
		self.rulesList = sHelper.addLabeledControl(_("Rules"), wx.ListBox)
		self.rulesList.Bind(wx.EVT_LISTBOX_DCLICK, self._onEdit)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button label in Attribra settings to add a rule.
		self.addBtn = wx.Button(self, label=_("Add…"))
		# Translators: Button label in Attribra settings to edit the selected rule.
		self.editBtn = wx.Button(self, label=_("Edit…"))
		# Translators: Button label in Attribra settings to delete the selected rule.
		self.delBtn = wx.Button(self, label=_("Delete"))
		# Translators: Button label in Attribra settings to reload rules from disk.
		self.reloadBtn = wx.Button(self, label=_("Reload"))

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
			# Translators: Prompt for entering an application (section) name. Example values are program executable names.
			_("Enter the application/section name (e.g. 'winword' or 'firefox')."),
			# Translators: Title of the dialog to add an application section.
			_("Add application"),
			"",
		)
		if dlg.ShowModal() == wx.ID_OK:
			name = self._normalizeSectionName(dlg.GetValue())
			if not name:
				# Translators: Message spoken when the user did not provide a required name.
				ui.message(_("Missing name."))
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
				# Translators: Message spoken when the application section already exists.
				ui.message(_("This application already exists."))
		dlg.Destroy()

	def _onDeleteSection(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		# 'global' is always shown; deleting it clears/removes stored rules.
		if section not in self.plugin.configs and section != "global":
			return
		msg = _("Are you sure you want to delete the application/section '{name}'? All rules in this section will be removed.").format(
			name=section
		)
		# Translators: Title of the confirmation dialog.
		res = wx.MessageBox(msg, _("Confirm"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
		if res != wx.YES:
			return
		self.plugin.configs.pop(section, None)
		self._refreshSections()
		self._selectSectionByName("global")
		# Translators: Message spoken after deleting an application section.
		ui.message(_("Application deleted."))

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

		# Translators: Title of the dialog to add a new rule.
		dlg = AttribraRuleDialog(self, _("Add rule"))
		# Translators: Title of the dialog to add a new rule.
		dlg = AttribraRuleDialog(self, _("Add rule"))
		if dlg.ShowModal() == wx.ID_OK:
			attr, valsText = dlg.getData()
			if not attr:
				# Translators: Message spoken when the attribute name field is empty.
				ui.message(_("Missing attribute name."))
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
		# Translators: Title of the dialog to edit an existing rule.
		dlg = AttribraRuleDialog(self, _("Edit rule"), attrName=attr, valuesText=currentText)
		if dlg.ShowModal() == wx.ID_OK:
			newAttr, valsText = dlg.getData()
			if not newAttr:
				# Translators: Message spoken when the attribute name field is empty.
				ui.message(_("Missing attribute name."))
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
		# Translators: Message spoken after reloading Attribra settings from disk.
		ui.message(_("Attribra settings reloaded."))

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
			# Translators: Message spoken after saving Attribra settings.
			ui.message(_("Attribra settings saved."))
		except Exception:
			log.exception("Error saving Attribra settings")
			# Translators: Message spoken when saving Attribra settings failed.
			ui.message(_("Save failed; see log for details."))


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	configs = {}
	currentPid = ""

	def __init__(self):
		# Translators: This add-on stores its configuration in an INI file located in the add-on folder.
		# Translators: Do not translate the file name "attribra.ini".
		addon = getCodeAddon()
		# Use the installed add-on path rather than a hard-coded folder name.
		self.configFile = os.path.join(addon.path, "attribra.ini")

		self.parsecfgs()  # parse configuration


		# Patch NVDA braille rendering hooks.
		# We patch unconditionally so changes take effect immediately after rules are created.
		# When no rules are configured, the patched hooks behave like NVDA defaults.
		self._patchBrailleHooks()

		# Register settings panel under a dedicated category.
		try:
			AttribraSettingsPanel._attribraPlugin = self
			if AttribraSettingsPanel not in settingsDialogs.NVDASettingsDialog.categoryClasses:
				settingsDialogs.NVDASettingsDialog.categoryClasses.append(AttribraSettingsPanel)
		except Exception:
			log.exception("Could not register Attribra settings panel")

		super(GlobalPlugin, self).__init__()



	def _patchBrailleHooks(self):
		"""Monkeypatch NVDA's braille TextInfoRegion to support Attribra rules.

		This is idempotent and safe to call multiple times.
		The method names in NVDA have changed over time; we patch whichever ones exist.
		"""
		if getattr(self, "_attribraHooksPatched", False):
			return

		# Resolve method names across NVDA versions.
		regionCls = braille.TextInfoRegion
		addName = "_addTextWithFields" if hasattr(regionCls, "_addTextWithFields") else "addTextWithFields"
		getTypeName = "_getTypeformFromFormatField" if hasattr(regionCls, "_getTypeformFromFormatField") else "getTypeformFromFormatField"
		updateName = "update"  # stable in practice

		missing = [n for n in (addName, getTypeName, updateName) if not hasattr(regionCls, n)]
		if missing:
			# If NVDA internals changed too much, fail gracefully and log it.
			log.error("Attribra: Cannot patch braille hooks; missing methods: %s" % ", ".join(missing))
			self._attribraHooksPatched = False
			return

		self._attribraHooksPatched = True
		self._attribraHookNames = {"add": addName, "getType": getTypeName, "update": updateName}

		# Keep originals so we can restore on terminate.
		self._orig_addTextWithFields = getattr(regionCls, addName)
		self._orig_update = getattr(regionCls, updateName)
		self._orig_getTypeform = getattr(regionCls, getTypeName)

		setattr(regionCls, addName, decorator(self._orig_addTextWithFields, "addTextWithFields"))
		setattr(regionCls, updateName, decorator(self._orig_update, "update"))
		setattr(regionCls, getTypeName, decorator(self._orig_getTypeform, "_getTypeformFromFormatField"))

		log.debug("Attribra: Patched braille hooks (%s, %s, %s)" % (addName, getTypeName, updateName))

	def _unpatchBrailleHooks(self):
		"""Restore NVDA's original braille hooks (best effort)."""
		if not getattr(self, "_attribraHooksPatched", False):
			return
		try:
			regionCls = braille.TextInfoRegion
			names = getattr(self, "_attribraHookNames", None) or {"add": "_addTextWithFields", "getType": "_getTypeformFromFormatField", "update": "update"}
			if hasattr(self, "_orig_addTextWithFields") and hasattr(regionCls, names["add"]):
				setattr(regionCls, names["add"], self._orig_addTextWithFields)
			if hasattr(self, "_orig_update") and hasattr(regionCls, names["update"]):
				setattr(regionCls, names["update"], self._orig_update)
			if hasattr(self, "_orig_getTypeform") and hasattr(regionCls, names["getType"]):
				setattr(regionCls, names["getType"], self._orig_getTypeform)
		except Exception:
			pass
		self._attribraHooksPatched = False


	def terminate(self):
		self._unpatchBrailleHooks()
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
		# Translators: Message spoken when toggling debug logging of TextInfo at the cursor. {state} is "start" or "stop".
		# Translators: The state toggled by the "log fields at cursor" command.
		state = _("start") if logTextInfo else _("stop")
		ui.message(_("Debug TextInfo logging: {state}").format(state=state))

	__gestures = {
		"kb:NVDA+control+a": "editConfig",
		"kb:NVDA+control+shift+a": "logFieldsAtCursor",
	}
