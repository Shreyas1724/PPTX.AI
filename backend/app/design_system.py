"""Consistent export tokens for all the existing PPTX.AI theme identifiers."""
from dataclasses import dataclass
from pptx.dml.color import RGBColor

@dataclass(frozen=True)
class Theme:
    background: str
    panel: str
    panel_alt: str
    ink: str
    secondary: str
    accent: str
    accent_two: str
    divider: str
    heading_font: str='Aptos Display'
    body_font: str='Aptos'
    def color(self,attr):
        raw=getattr(self,attr).lstrip('#')
        return RGBColor.from_string(raw.upper())

THEMES={
 'midnight':Theme('0C1325','18233B','212D49','F7F9FF','AAB8CF','9B8AFB','59D3C1','33425F'),
 'light':Theme('F6F8FC','FFFFFF','E9EEF6','1A2742','61708B','6356C8','138C9C','D9E1ED'),
 'aurora':Theme('0B1E2B','163542','234452','F0FFFC','B4CFCE','42E1B8','7CB8FF','34525D'),
}

def get_theme(name:str)->Theme:
    return THEMES.get(name,THEMES['midnight'])
