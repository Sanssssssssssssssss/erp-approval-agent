from src.backend.domains.erp_approval.connectors.base import ErpReadOnlyConnector
from src.backend.domains.erp_approval.connectors.config import (
    connector_selection_summary,
    load_erp_connector_config_from_env,
    redacted_connector_config,
)
from src.backend.domains.erp_approval.connectors.coverage import build_replay_coverage_matrix
from src.backend.domains.erp_approval.connectors.coverage_models import (
    ErpConnectorReplayCoverageItem,
    ErpConnectorReplayCoverageSummary,
)
from src.backend.domains.erp_approval.connectors.diagnostics import (
    ErpConnectorDiagnostic,
    ErpConnectorHealthSummary,
    ErpConnectorProviderProfileSummary,
)
from src.backend.domains.erp_approval.connectors.http_readonly import HttpReadOnlyErpConnector
from src.backend.domains.erp_approval.connectors.mappers import (
    map_provider_payload_to_records,
    normalize_provider_payload,
    source_id_for_provider,
)
from src.backend.domains.erp_approval.connectors.models import (
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpConnectorConfig,
    ErpConnectorProvider,
    ErpReadOperation,
    ErpReadRequest,
    ErpReadResult,
)
from src.backend.domains.erp_approval.connectors.provider_profiles import (
    FORBIDDEN_WRITE_METHODS,
    PROVIDER_PROFILES,
    profile_for,
    supported_operations_for,
)
from src.backend.domains.erp_approval.connectors.replay import (
    list_provider_fixtures,
    load_provider_fixture,
    replay_provider_fixture,
    validate_replay_record,
)
from src.backend.domains.erp_approval.connectors.replay_models import (
    ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    ErpConnectorReplayFixtureInfo,
    ErpConnectorReplayRecord,
    ErpConnectorReplayRequest,
    ErpConnectorReplaySummary,
    ErpConnectorReplayValidation,
)

__all__ = [
    "ERP_CONNECTOR_NON_ACTION_STATEMENT",
    "ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT",
    "FORBIDDEN_WRITE_METHODS",
    "PROVIDER_PROFILES",
    "ErpConnectorConfig",
    "ErpConnectorDiagnostic",
    "ErpConnectorHealthSummary",
    "ErpConnectorProvider",
    "ErpConnectorProviderProfileSummary",
    "ErpConnectorReplayFixtureInfo",
    "ErpConnectorReplayCoverageItem",
    "ErpConnectorReplayCoverageSummary",
    "ErpConnectorReplayRecord",
    "ErpConnectorReplayRequest",
    "ErpConnectorReplaySummary",
    "ErpConnectorReplayValidation",
    "ErpReadOnlyConnector",
    "ErpReadOperation",
    "ErpReadRequest",
    "ErpReadResult",
    "HttpReadOnlyErpConnector",
    "connector_selection_summary",
    "build_replay_coverage_matrix",
    "load_erp_connector_config_from_env",
    "list_provider_fixtures",
    "load_provider_fixture",
    "map_provider_payload_to_records",
    "normalize_provider_payload",
    "profile_for",
    "redacted_connector_config",
    "replay_provider_fixture",
    "source_id_for_provider",
    "supported_operations_for",
    "validate_replay_record",
]
