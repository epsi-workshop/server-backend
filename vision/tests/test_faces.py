from vision.faces import Face, FaceEvents

ALICE = Face(box=(0, 0, 80, 80), score=0.9, member_id="a", name="Alice", similarity=0.6)
STRANGER = Face(box=(100, 0, 80, 80), score=0.9, similarity=0.1)


def test_known_face_needs_confirmation():
    ev = FaceEvents(confirm=2, cooldown_s=30)
    assert ev.update([ALICE], 0) == []
    assert ev.update([ALICE], 0.3) == [ALICE]


def test_cooldown_then_signaled_again():
    ev = FaceEvents(confirm=1, cooldown_s=30)
    assert ev.update([ALICE], 0) == [ALICE]
    assert ev.update([ALICE], 10) == []
    assert ev.update([ALICE], 31) == [ALICE]


def test_streak_resets_when_face_leaves():
    ev = FaceEvents(confirm=2)
    ev.update([ALICE], 0)
    ev.update([], 0.3)
    assert ev.update([ALICE], 0.6) == []


def test_unknown_needs_more_frames():
    ev = FaceEvents(confirm=2, confirm_unknown=4, known_grace_s=0)
    assert [ev.update([STRANGER], t) for t in (0, 1, 2)] == [[], [], []]
    assert ev.update([STRANGER], 3) == [STRANGER]


def test_unknown_suppressed_right_after_a_member():
    # Un membre de profil donne quelques images « inconnu » : pas d'alerte intrus juste après l'avoir reconnu.
    ev = FaceEvents(confirm=1, confirm_unknown=1, known_grace_s=5)
    assert ev.update([ALICE], 0) == [ALICE]
    assert ev.update([STRANGER], 2) == []
    assert ev.update([STRANGER], 6) == [STRANGER]


def test_best_match_kept_for_duplicate_identity():
    ev = FaceEvents(confirm=1)
    weak = Face(box=(0, 0, 50, 50), score=0.9, member_id="a", name="Alice", similarity=0.4)
    assert ev.update([weak, ALICE], 0) == [ALICE]
