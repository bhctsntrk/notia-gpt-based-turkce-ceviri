-- Turkish GUI font binding v1
local cheatgui_tr_font = "mods/translation_tr_witty/fonts/font_pixel.xml"
local cheatgui_native_text = GuiText
local cheatgui_native_button = GuiButton

local function GuiText(gui, x, y, text)
  return cheatgui_native_text(gui, x, y, text, 1, cheatgui_tr_font, true)
end

-- Cheatgui uses the legacy argument order; call the engine in its current order.
local function GuiButton(gui, x, y, text, id)
  return cheatgui_native_button(gui, id, x, y, text, 1, cheatgui_tr_font, true)
end
