from clipgauge_pipeline.camera import director


def test_group_composition_uses_a_padded_union_box():
    box = director.composition_box([
        {"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.3},
        {"x": 0.6, "y": 0.25, "w": 0.2, "h": 0.3},
    ])

    assert box is not None
    assert box[0] < 0.1
    assert box[2] > 0.7


def test_camera_purpose_does_not_force_faces_into_environment_shots():
    assert director.shot_purpose(face_count=0, speaking_count=0) == "environment"
    assert director.shot_purpose(face_count=2, speaking_count=2) == "group"
    assert director.shot_purpose(face_count=1, speaking_count=1) == "speaker"
