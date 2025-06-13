import json
from pathlib import Path
import os

from starlette.applications import Starlette

from f5_ai_gateway_sdk.processor_routes import ProcessorRoutes

from pangea.config import PangeaConfig
from pangea.services import ai_guard as aig

from pangea_f5_ai_gateway_processor.processor import AIGuardProcessor

def app():
    return app_from_config(Path(os.environ["PANGEA_CONFIG_PATH"]))


def app_from_config(config_path: Path):
    with open(config_path, "r") as fp:
        config = json.load(fp)

    cfg = PangeaConfig(
        base_url_template=config["base_url_template"]
    )

    ai_guard = aig.AIGuard(
        token=config["ai_guard_api_token"],
        config=cfg,
    )

    return Starlette(
        routes=ProcessorRoutes([AIGuardProcessor(ai_guard)]),
    )
