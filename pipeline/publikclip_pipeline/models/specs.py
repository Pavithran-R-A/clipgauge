"""Concrete, immutable model registry entries.

Hashes were calculated from complete staged downloads on 2026-08-19 and are
also recorded in pipeline/runtime-manifest.json. Libraries that fetch models
internally (for example faster-whisper through HF_HOME) remain outside this
explicit registry boundary and are documented rather than falsely presented
as covered here.
"""

from .registry import ModelSpec, register

LAUGHTER = register(
    ModelSpec(
        name="laughter-jrgillick",
        filename="best.pth.tar",
        url=(
            "https://raw.githubusercontent.com/jrgillick/laughter-detection/"
            "5d5e0327916959d832d95ffbef5f484efc93d799/checkpoints/in_use/"
            "resnet_with_augmentation/best.pth.tar"
        ),
        sha256="bfe450e41926a4e9de2abf007c9a13fa8420439eaa1383e986563c565f5ef206",
        approx_mb=10,
        revision="5d5e0327916959d832d95ffbef5f484efc93d799",
        license="Upstream repository license; verify before redistribution",
    )
)
PANNS_CNN14_MAX = register(
    ModelSpec(
        name="panns-cnn14-decisionlevelmax",
        filename="Cnn14_DecisionLevelMax.pth",
        url=(
            "https://zenodo.org/records/3987831/files/"
            "Cnn14_DecisionLevelMax_mAP%3D0.385.pth?download=1"
        ),
        sha256="dd3b4043a87d4ec13df8082c0fcfee3fb5084151808e47e060987a95eabdd142",
        approx_mb=313,
        revision="Zenodo record 3987831",
        license="Zenodo record license; verify before redistribution",
    )
)
CAMPPLUS = register(
    ModelSpec(
        name="campplus",
        filename="campplus_cn_common.bin",
        url=(
            "https://huggingface.co/funasr/campplus/resolve/"
            "e4b6ede7ce16997aff4ae69fbca1f0175e2afede/campplus_cn_common.bin"
        ),
        sha256="3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8",
        approx_mb=28,
        revision="e4b6ede7ce16997aff4ae69fbca1f0175e2afede",
        license="Hugging Face repository license; verify before redistribution",
    )
)
ULTRAFACE = register(
    ModelSpec(
        name="ultraface",
        filename="ultraface-rfb-320.onnx",
        url=(
            "https://raw.githubusercontent.com/JeremySNR/clip-forge/"
            "7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/"
            "ultraface-rfb-320.onnx"
        ),
        sha256="34cd7e60aeff28744c657de7a3dc64e872d506741de66987f3426f2b79f88017",
        approx_mb=2,
        revision="7a935022a2396eb5b24f67b588945133dcb511fc",
        license="Upstream repository license; verify before redistribution",
    )
)
LR_ASD_FRONTEND = register(
    ModelSpec(
        name="lr-asd",
        filename="frontend.onnx",
        url=(
            "https://raw.githubusercontent.com/JeremySNR/clip-forge/"
            "7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/"
            "lr-asd-frontend.onnx"
        ),
        sha256="f7c055612cd6f1f2da3ab8257567ab68a6b0d69b5e436699a5cf65334dd79461",
        approx_mb=3,
        revision="7a935022a2396eb5b24f67b588945133dcb511fc",
        license="Upstream repository license; verify before redistribution",
    )
)
LR_ASD_BACKEND = register(
    ModelSpec(
        name="lr-asd",
        filename="backend.onnx",
        url=(
            "https://raw.githubusercontent.com/JeremySNR/clip-forge/"
            "7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/"
            "lr-asd-backend.onnx"
        ),
        sha256="9453caa09998027995664fd5a3b1fab4ad0de30a92c6beba8c29c3619de510a9",
        approx_mb=1,
        revision="7a935022a2396eb5b24f67b588945133dcb511fc",
        license="Upstream repository license; verify before redistribution",
    )
)
