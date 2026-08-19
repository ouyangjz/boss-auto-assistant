from app.utils.file_utils import sanitize_filename


def test_sanitize_filename_removes_windows_invalid_chars():
    assert sanitize_filename('A/B:C*D?E"F<G>H|I') == "A_B_C_D_E_F_G_H_I"
