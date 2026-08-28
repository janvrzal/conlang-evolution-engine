import pytest
from cee.engine.phonology import FeatureMapper

def test_mapper_roundtrip():
    mapper = FeatureMapper()
    
    # 1. Zkusíme přeložit klasické latinské slovo do rysových matic
    word = mapper.parse_word(concept_id="1", ipa_string="pater")
    
    # Slovo by mělo mít 5 segmentů
    assert len(word.segments) == 5
    
    # Zkontrolujeme, že první segment /p/ má správné rysy (neznělé, plozivní, retné)
    p_features = word.segments[0].features
    assert p_features['son'] == '-'   # Není to sonorní hláska
    assert p_features['voi'] == '-' # Je neznělá
    assert p_features['cont'] == '-'  # Není kontinuální (je to okluzíva)
    
    # 2. Zkontrolujeme renderování (rysy -> IPA) beze změny
    rendered = mapper.render_word(word)
    assert rendered == "pater"

def test_lenition_rule_simulation():
    mapper = FeatureMapper()
    word = mapper.parse_word(concept_id="1", ipa_string="pater")
    
    # Simulace historické hláskové změny (intervokalická lenice t -> d)
    # Vezmeme třetí segment (/t/) a změníme mu rys znělosti na '+'
    t_segment = word.segments[2]
    assert mapper.segment_to_ipa(t_segment) == "t"
    
    t_segment.features['voi'] = '+' # Znělost ON
    
    # Mapper by teď měl rysovou matici interpretovat jako /d/
    assert mapper.segment_to_ipa(t_segment) == "d"
    
    # A celé slovo by se mělo vyrenderovat jako "pader"
    assert mapper.render_word(word) == "pader"
