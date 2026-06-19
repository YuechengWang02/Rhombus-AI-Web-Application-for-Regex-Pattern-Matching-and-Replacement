"""Server-side storage of dataframes as parquet snapshots.

Each :class:`~datasets.models.Dataset` owns exactly one parquet file named by
its UUID under ``settings.DATA_STORE_DIR``. Transformations overwrite this file
in place (after recording history), so it always reflects current state.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from django.conf import settings

from config.exceptions import NotFoundError


def path_for(dataset_id) -> Path:
    """Absolute parquet path for a dataset id."""
    return Path(settings.DATA_STORE_DIR) / f"{dataset_id}.parquet"


def save_dataframe(dataset_id, df: pd.DataFrame) -> str:
    """Write *df* to the dataset's parquet file and return the path as a string."""
    target = path_for(dataset_id)
    # Parquet preserves dtypes and is fast to re-read; index is not needed.
    df.to_parquet(target, index=False)
    return str(target)


def load_dataframe(dataset_id) -> pd.DataFrame:
    """Load the stored dataframe, or raise NotFoundError if the file is gone."""
    target = path_for(dataset_id)
    if not target.exists():
        raise NotFoundError(
            "The data for this upload is no longer available (it may have expired)."
        )
    return pd.read_parquet(target)


def delete_dataframe(dataset_id) -> None:
    """Remove the parquet file if present (used by TTL cleanup)."""
    path_for(dataset_id).unlink(missing_ok=True)


def _backup_path(dataset_id, transform_id) -> Path:
    return Path(settings.DATA_STORE_DIR) / f"{dataset_id}.bak.{transform_id}.parquet"


def save_backup(dataset_id, transform_id, df: pd.DataFrame) -> None:
    """Snapshot the pre-transform state so a transform can be undone."""
    df.to_parquet(_backup_path(dataset_id, transform_id), index=False)


def restore_backup(dataset_id, transform_id) -> pd.DataFrame:
    """Restore a backup as the current dataframe and return it."""
    backup = _backup_path(dataset_id, transform_id)
    if not backup.exists():
        raise NotFoundError("No undo snapshot is available for this transformation.")
    df = pd.read_parquet(backup)
    save_dataframe(dataset_id, df)
    backup.unlink(missing_ok=True)
    return df


def delete_backup(dataset_id, transform_id) -> None:
    _backup_path(dataset_id, transform_id).unlink(missing_ok=True)
