# OpenRelik
![Unit tests](https://github.com/openrelik/openrelik-server/actions/workflows/python-test.yaml/badge.svg)

## Digital Forensics Workflow Server
OpenRelik is an open-source (Apache-2.0) platform designed to streamline collaborative digital forensic investigations. It combines modular workflows for custom investigative processes, an intuitive interface for efficient workflow management, real-time collaboration features, and a centralized repository for shared artifacts. The platform is easy to extend with new workers to adapt to evolving forensic needs.

##### Obligatory Fine Print
This is not an official Google product (experimental or otherwise), it is just code that happens to be owned by Google.

---

## External Read-Only Data Stores

### Overview

External read-only data stores let you register files from locations that already exist on disk — SMB shares, NFS mounts, pre-existing case storage — without copying any data into the main OpenRelik volume. An `ExternalStorage` record maps a logical name (e.g. `case_smb`) to an absolute mount point on the host/container (e.g. `/mnt/cases`). Files registered from that store are treated as read-only references: workers can read them as normal `File` objects, but the platform never writes to or deletes them from disk.

### API Endpoints

All endpoints are under `/api/v1/datastores/` and require an authenticated user.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/datastores/` | List all configured external storage locations. |
| `POST` | `/api/v1/datastores/` | Create a new external storage (requires `name`, `mount_point`, optional `description`). Returns `409` if the name already exists. |
| `GET` | `/api/v1/datastores/{name}` | Get a single external storage by name. |
| `PATCH` | `/api/v1/datastores/{name}` | Update `mount_point` and/or `description`. |
| `DELETE` | `/api/v1/datastores/{name}` | Delete a storage configuration. Returns `409` if any files still reference it. |
| `POST` | `/api/v1/datastores/{name}/files` | Register an existing file into the virtual filesystem. Supply `relative_path` (relative to the mount point), `folder_id`, and optional `display_name`/`extension`. No data is copied; a `File` DB record is created pointing at the original location. |
| `GET` | `/api/v1/datastores/{name}/browse?path=` | List the contents of a directory inside the storage. `path` is relative to the mount point; omit it to list the root. Returns directories and files with sizes, sorted directories-first. |

Path traversal (`..` components and symlink escapes) is rejected with `400` on both the register and browse endpoints.

### Database Changes

**New table — `ExternalStorage`**

| Column | Type | Notes |
|--------|------|-------|
| `name` | `UnicodeText` | Unique logical identifier (primary lookup key). |
| `mount_point` | `UnicodeText` | Absolute path on the host/container. |
| `description` | `UnicodeText` (nullable) | Human-readable label. |

The table also inherits the standard `BaseModel` columns (`id`, `created_at`, `updated_at`, `is_deleted`).

**New columns on `File`**

| Column | Type | Notes |
|--------|------|-------|
| `external_storage_name` | `UnicodeText` FK → `externalstorage.name` | Set when the file lives in an external store; `NULL` for normal files. |
| `external_relative_path` | `UnicodeText` (nullable) | Path relative to `ExternalStorage.mount_point`. |

A derived property `is_external` returns `True` when `external_storage_name` is set.

### How It Works

`File.path` is a `hybrid_property` that resolves the on-disk location at runtime:

1. **External file** (`external_storage_name` is set): returns `mount_point / external_relative_path`, after validating that there are no `..` components. The `ExternalStorage` relationship must be eagerly loaded for this to work.
2. **Explicit storage provider** (`storage_provider` is set): looks up the provider's base path from config and joins it with `storage_key`.
3. **Default** (most files): constructs `folder.path / <uuid>[.extension]` using the parent folder's path recursively.

On soft-delete, the standard SQLAlchemy `after_delete` event removes the file from disk for normal files. External files are skipped — the listener returns early when `external_storage_name` is set, so the original data on the mount is never touched.
