# -*- coding: utf-8 -*-

#AttriBra Addon for NVDA
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2017 Alberto Zanella <lapostadialberto@gmail.com>
#
# Extended with an easy to use interface (Attribra) to edit attribra.ini without manual editing.
#Copyright 2025 Vince Jansen <jansen.vince@gmail.com>
import os

import addonHandler
addonHandler.initTranslation()
from addonHandler import getCodeAddon  

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


class AttribraSettingsDialog(settingsDialogs.SettingsDialog):
	# Translators: Title of the dialog containing the Attribra settings.
	title = _("Textattribute settings.")

	_STANDARD_ATTRIBUTES = (
		("bold", "Bold"),
		("underline", "Underline"),
		("italic", "Italic"),
		("invalid-spelling", "Spelling errors"),
	)

	def makeSettings(self, settingsSizer):
		self.plugin = getattr(self, "_attribraPlugin", None)
		self._updatingControls = False
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# Translators: Label for the list of application-specific configuration sections in Attribra settings.
		self.sectionChoice = sHelper.addLabeledControl(_("Section / Application"), wx.Choice)
		self.sectionChoice.Bind(wx.EVT_CHOICE, self._onSectionChanged)

		sectionBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button label in Attribra settings to add an application-specific section.
		self.addSectionBtn = wx.Button(self, label=_("Add application…"))
		# Translators: Button label in Attribra settings to delete an application-specific section.
		self.delSectionBtn = wx.Button(self, label=_("Delete application"))
		self.addSectionBtn.Bind(wx.EVT_BUTTON, self._onAddSection)
		self.delSectionBtn.Bind(wx.EVT_BUTTON, self._onDeleteSection)
		sectionBtnSizer.Add(self.addSectionBtn, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sectionBtnSizer.Add(self.delSectionBtn, 0)
		sHelper.addItem(sectionBtnSizer)

		# Translators: Label for the group of standard text attributes that can be marked on a braille display.
		attributesBox = wx.StaticBox(self, label=_("Text attributes"))
		attributesSizer = wx.StaticBoxSizer(attributesBox, wx.VERTICAL)
		self.attributeCheckboxes = {}

		# Translators: Checkbox label for marking bold text on a braille display.
		self.boldCheckBox = wx.CheckBox(self, label=_("Bold"))
		self.attributeCheckboxes["bold"] = self.boldCheckBox
		# Translators: Checkbox label for marking underlined text on a braille display.
		self.underlineCheckBox = wx.CheckBox(self, label=_("Underline"))
		self.attributeCheckboxes["underline"] = self.underlineCheckBox
		# Translators: Checkbox label for marking italic text on a braille display.
		self.italicCheckBox = wx.CheckBox(self, label=_("Italic"))
		self.attributeCheckboxes["italic"] = self.italicCheckBox
		# Translators: Checkbox label for marking spelling errors on a braille display.
		self.spellingErrorsCheckBox = wx.CheckBox(self, label=_("Spelling errors"))
		self.attributeCheckboxes["invalid-spelling"] = self.spellingErrorsCheckBox

		for attrName, checkBox in self.attributeCheckboxes.items():
			# wx.CheckBox does not implement SetClientData in wxPython.
			# Store the NVDA format-field name directly on the control instead.
			checkBox._attribraAttrName = attrName
			checkBox.Bind(wx.EVT_CHECKBOX, self._onAttributeToggled)
			attributesSizer.Add(checkBox, 0, wx.ALL, guiHelper.BORDER_FOR_DIALOGS)
		sHelper.addItem(attributesSizer)

		# Translators: Label for advanced Attribra rules not represented by the standard checkboxes.
		self.rulesList = sHelper.addLabeledControl(_("Advanced rules"), wx.ListBox)
		self.rulesList.Bind(wx.EVT_LISTBOX_DCLICK, self._onEdit)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button label in Attribra settings to add an advanced rule.
		self.addBtn = wx.Button(self, label=_("Add…"))
		# Translators: Button label in Attribra settings to edit the selected advanced rule.
		self.editBtn = wx.Button(self, label=_("Edit…"))
		# Translators: Button label in Attribra settings to delete the selected advanced rule.
		self.delBtn = wx.Button(self, label=_("Delete"))
		# Translators: Button label in Attribra settings to reload all settings from disk.
		self.reloadBtn = wx.Button(self, label=_("Reload"))

		self.addBtn.Bind(wx.EVT_BUTTON, self._onAdd)
		self.editBtn.Bind(wx.EVT_BUTTON, self._onEdit)
		self.delBtn.Bind(wx.EVT_BUTTON, self._onDelete)
		self.reloadBtn.Bind(wx.EVT_BUTTON, self._onReload)
		for button in (self.addBtn, self.editBtn, self.delBtn, self.reloadBtn):
			btnSizer.Add(button, 0, wx.RIGHT, guiHelper.BORDER_FOR_DIALOGS)
		sHelper.addItem(btnSizer)

		self._refreshSections()

	def postInit(self):
		"""Place keyboard focus on the application selector."""
		self.sectionChoice.SetFocus()

	def _normalizeSectionName(self, name: str) -> str:
		return (name or "").strip()

	def _selectSectionByName(self, name: str):
		items = list(self.sectionChoice.GetItems())
		try:
			idx = items.index(name)
		except ValueError:
			return
		self.sectionChoice.SetSelection(idx)
		self._refreshControls()

	def _refreshSections(self):
		current = self._currentSection() if self.sectionChoice.GetCount() else "global"
		sections = sorted(set(self.plugin.configs.keys()) | {"global"}) if self.plugin else ["global"]
		self.sectionChoice.SetItems(sections)
		self.sectionChoice.SetSelection(sections.index(current) if current in sections else sections.index("global"))
		self._refreshControls()

	def _onAddSection(self, evt):
		if not self.plugin:
			return
		dlg = wx.TextEntryDialog(
			self,
			# Translators: Prompt for entering an application section name. Examples are executable base names.
			_("Enter the application/section name (e.g. 'winword' or 'firefox')."),
			# Translators: Title of the dialog to add an application section.
			_("Add application"),
			"",
		)
		try:
			if dlg.ShowModal() != wx.ID_OK:
				return
			name = self._normalizeSectionName(dlg.GetValue())
			if not name:
				# Translators: Message spoken when the user did not provide a required application name.
				ui.message(_("Missing name."))
				return
			existing = next((s for s in self.plugin.configs if s.lower() == name.lower()), None)
			if existing is None:
				self.plugin.configs[name] = {}
				existing = name
			else:
				# Translators: Message spoken when the application section already exists.
				ui.message(_("This application already exists."))
			self._refreshSections()
			self._selectSectionByName(existing)
		finally:
			dlg.Destroy()

	def _onDeleteSection(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		# Translators: Confirmation message shown before deleting an application section. {name} is the section name.
		msg = _("Are you sure you want to delete the application/section '{name}'? All rules in this section will be removed.").format(name=section)
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
		return "global" if i == wx.NOT_FOUND else self.sectionChoice.GetString(i)

	def _ensureSectionExists(self, section):
		if section not in self.plugin.configs:
			self.plugin.configs[section] = {}

	def _refreshControls(self):
		self._updatingControls = True
		self.Freeze()
		try:
			section = self._currentSection()
			mapping = (self.plugin.configs.get(section) if self.plugin else None) or {}
			for attrName, checkBox in self.attributeCheckboxes.items():
				checkBox.SetValue(attrName in mapping and True in mapping[attrName])
			advancedItems = []
			for attr, vals in sorted(mapping.items(), key=lambda item: item[0].lower()):
				if attr not in self.attributeCheckboxes:
					advancedItems.append(f"{attr} = {_list_to_ini_value(vals)}")
			self.rulesList.SetItems(advancedItems)
			if advancedItems:
				self.rulesList.SetSelection(0)
			else:
				self.rulesList.SetSelection(wx.NOT_FOUND)
			self.Layout()
		finally:
			self.Thaw()
			self._updatingControls = False

	def _onSectionChanged(self, evt):
		self._refreshControls()

	def _onAttributeToggled(self, evt):
		if self._updatingControls or not self.plugin:
			return
		checkBox = evt.GetEventObject()
		attrName = getattr(checkBox, "_attribraAttrName", None)
		if not attrName:
			log.error("Attribra: Checkbox event without an attribute name")
			return
		section = self._currentSection()
		self._ensureSectionExists(section)
		if checkBox.IsChecked():
			self.plugin.configs[section][attrName] = _parse_value_to_list("1")
		else:
			self.plugin.configs[section].pop(attrName, None)

	def _selectedAttr(self):
		section = self._currentSection()
		mapping = (self.plugin.configs.get(section) if self.plugin else None) or {}
		sel = self.rulesList.GetSelection()
		if sel == wx.NOT_FOUND:
			return None, None
		line = self.rulesList.GetString(sel)
		attr = line.split("=", 1)[0].strip() if "=" in line else ""
		return (attr, mapping.get(attr)) if attr else (None, None)

	def _onAdd(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		self._ensureSectionExists(section)
		# Translators: Title of the dialog to add an advanced rule.
		dlg = AttribraRuleDialog(self, _("Add rule"))
		try:
			if dlg.ShowModal() == wx.ID_OK:
				attr, valsText = dlg.getData()
				if not attr:
					# Translators: Message spoken when the attribute name field is empty.
					ui.message(_("Missing attribute name."))
					return
				self.plugin.configs[section][attr] = _parse_value_to_list(valsText)
				self._refreshControls()
		finally:
			dlg.Destroy()

	def _onEdit(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		attr, vals = self._selectedAttr()
		if not attr:
			return
		# Translators: Title of the dialog to edit an advanced rule.
		dlg = AttribraRuleDialog(self, _("Edit rule"), attrName=attr, valuesText=_list_to_ini_value(vals or []))
		try:
			if dlg.ShowModal() == wx.ID_OK:
				newAttr, valsText = dlg.getData()
				if not newAttr:
					# Translators: Message spoken when the attribute name field is empty.
					ui.message(_("Missing attribute name."))
					return
				if newAttr != attr:
					self.plugin.configs[section].pop(attr, None)
				self.plugin.configs[section][newAttr] = _parse_value_to_list(valsText)
				self._refreshControls()
		finally:
			dlg.Destroy()

	def _onDelete(self, evt):
		if not self.plugin:
			return
		section = self._currentSection()
		attr, _vals = self._selectedAttr()
		if attr:
			self.plugin.configs.get(section, {}).pop(attr, None)
			self._refreshControls()

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

	def onOk(self, evt):
		"""Save Attribra settings and close the dialog."""
		self.onSave()
		super().onOk(evt)


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

		super().__init__()

		# Add an Attribra button to NVDA's existing Braille category.
		# Attribra deliberately does not register a separate settings category.
		self._patchBrailleSettingsPanel()


	def _patchBrailleSettingsPanel(self):
		"""Add a button for Attribra to NVDA's Braille settings category."""
		panelCls = settingsDialogs.BrailleSettingsPanel
		currentMakeSettings = panelCls.makeSettings
		# Replace an older Attribra wrapper after an add-on reload. This ensures
		# the button always refers to the current GlobalPlugin instance.
		if getattr(currentMakeSettings, "_attribraWrapper", False):
			currentMakeSettings = getattr(currentMakeSettings, "_attribraOriginal", currentMakeSettings)
			panelCls.makeSettings = currentMakeSettings

		plugin = self
		self._origBrailleMakeSettings = currentMakeSettings

		def makeSettingsWithAttribra(panel, settingsSizer):
			currentMakeSettings(panel, settingsSizer)
			# Translators: Label for a button in NVDA's Braille settings that opens the Attribra configuration dialog.
			panel.attribraSettingsButton = wx.Button(panel, label=_("Textattribute settings…"))
			panel.attribraSettingsButton.Bind(
				wx.EVT_BUTTON,
				lambda evt: plugin._openAttribraSettingsDialog(panel),
			)
			settingsSizer.Add(
				panel.attribraSettingsButton,
				flag=wx.TOP | wx.ALIGN_LEFT,
				border=guiHelper.BORDER_FOR_DIALOGS,
			)

		makeSettingsWithAttribra._attribraWrapper = True
		makeSettingsWithAttribra._attribraOriginal = currentMakeSettings
		panelCls.makeSettings = makeSettingsWithAttribra

	def _unpatchBrailleSettingsPanel(self):
		"""Restore NVDA's original Braille settings builder."""
		try:
			panelCls = settingsDialogs.BrailleSettingsPanel
			current = panelCls.makeSettings
			if getattr(current, "_attribraWrapper", False):
				panelCls.makeSettings = getattr(current, "_attribraOriginal", self._origBrailleMakeSettings)
		except Exception:
			log.exception("Could not remove the Attribra button from Braille settings")

	def _openAttribraSettingsDialog(self, parent):
		"""Open Attribra settings as a modal dialog from the Braille category."""
		AttribraSettingsDialog._attribraPlugin = self
		try:
			dlg = AttribraSettingsDialog(parent, resizeable=True, multiInstanceAllowed=True)
		except Exception:
			log.exception("Could not create Attribra settings dialog")
			# Translators: Message spoken when the Attribra settings dialog could not be opened.
			ui.message(_("Could not open Attribra settings."))
			return
		dlg.ShowModal()

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
		self._unpatchBrailleSettingsPanel()
		self._unpatchBrailleHooks()
		AttribraSettingsDialog._attribraPlugin = None
		super().terminate()

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
