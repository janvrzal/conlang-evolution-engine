from cee.engine.phonotactics import PhonotacticProfile


def test_profil_se_uci_z_vlastniho_lexikonu(mapper):
    profile = PhonotacticProfile.learn(
        [mapper.parse_word("open", "pata"), mapper.parse_word("closed", "pat")]
    )

    assert profile.max_onset == 1
    assert profile.max_coda == 1
    assert profile.violation(mapper.parse_word("valid", "pata")) is None
    assert profile.violation(mapper.parse_word("cluster", "pstra")) == "onset_cluster"


def test_profil_opravi_jen_shluk_ktery_sam_nepovoluje(mapper):
    profile = PhonotacticProfile.learn([mapper.parse_word("model", "pata")])
    word = mapper.parse_word("cluster", "pstra")

    assert profile.repair(word) is True
    assert len(word.syllable_nuclei()) == 2
