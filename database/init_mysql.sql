-- AI Video Workflow - MySQL 8.x initialization
-- Default account: admin / admin123
-- The password below is stored as a BCrypt hash, never as plaintext.

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `ai_video`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `ai_video`;

CREATE TABLE IF NOT EXISTS `sys_user` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(64) NOT NULL,
    `password_hash` VARCHAR(255) NOT NULL,
    `nickname` VARCHAR(100) NOT NULL DEFAULT '',
    `status` VARCHAR(20) NOT NULL DEFAULT 'ENABLED',
    `last_login_time` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_sys_user_username` (`username`),
    KEY `ix_sys_user_username` (`username`),
    KEY `ix_sys_user_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_project` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `cover_file_id` BIGINT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_project_name` (`name`),
    KEY `ix_ai_project_status` (`status`),
    KEY `ix_ai_project_created_by` (`created_by`),
    CONSTRAINT `fk_ai_project_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_file` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NULL,
    `file_name` VARCHAR(255) NOT NULL,
    `original_name` VARCHAR(255) NOT NULL,
    `file_type` VARCHAR(20) NOT NULL,
    `mime_type` VARCHAR(100) NOT NULL,
    `file_size` BIGINT NOT NULL,
    `storage_type` VARCHAR(20) NOT NULL DEFAULT 'LOCAL',
    `storage_path` VARCHAR(500) NOT NULL,
    `url` VARCHAR(500) NOT NULL,
    `thumbnail_url` VARCHAR(500) NULL,
    `width` INT NULL,
    `height` INT NULL,
    `duration` FLOAT NULL,
    `source_type` VARCHAR(30) NOT NULL DEFAULT 'UPLOAD',
    `source_id` BIGINT NULL,
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_file_project_id` (`project_id`),
    KEY `ix_ai_file_file_name` (`file_name`),
    KEY `ix_ai_file_file_type` (`file_type`),
    KEY `ix_ai_file_source_type` (`source_type`),
    KEY `ix_ai_file_created_by` (`created_by`),
    CONSTRAINT `fk_ai_file_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_file_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_model_config` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(150) NOT NULL,
    `model_type` VARCHAR(20) NOT NULL,
    `provider` VARCHAR(60) NOT NULL,
    `base_url` VARCHAR(500) NULL,
    `model_name` VARCHAR(150) NOT NULL,
    `api_key_encrypted` TEXT NULL,
    `api_key_env` VARCHAR(100) NULL,
    `extra_config` JSON NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ENABLED',
    `is_default` TINYINT(1) NOT NULL DEFAULT 0,
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_model_config_name` (`name`),
    KEY `ix_ai_model_config_model_type` (`model_type`),
    KEY `ix_ai_model_config_status` (`status`),
    KEY `ix_ai_model_config_created_by` (`created_by`),
    CONSTRAINT `fk_ai_model_config_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_prompt` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NULL,
    `name` VARCHAR(150) NOT NULL,
    `prompt_type` VARCHAR(30) NOT NULL,
    `content` TEXT NOT NULL,
    `negative_prompt` TEXT NULL,
    `variables` JSON NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ENABLED',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_prompt_project_id` (`project_id`),
    KEY `ix_ai_prompt_name` (`name`),
    KEY `ix_ai_prompt_prompt_type` (`prompt_type`),
    KEY `ix_ai_prompt_status` (`status`),
    KEY `ix_ai_prompt_created_by` (`created_by`),
    CONSTRAINT `fk_ai_prompt_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_prompt_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_character` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `appearance` TEXT NULL,
    `personality` TEXT NULL,
    `reference_file_id` BIGINT NULL,
    `prompt_id` BIGINT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_character_project_id` (`project_id`),
    KEY `ix_ai_character_name` (`name`),
    KEY `ix_ai_character_status` (`status`),
    KEY `ix_ai_character_created_by` (`created_by`),
    CONSTRAINT `fk_ai_character_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_character_reference_file_id`
        FOREIGN KEY (`reference_file_id`) REFERENCES `ai_file` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_character_prompt_id`
        FOREIGN KEY (`prompt_id`) REFERENCES `ai_prompt` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_character_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_scene` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `environment` TEXT NULL,
    `atmosphere` TEXT NULL,
    `reference_file_id` BIGINT NULL,
    `prompt_id` BIGINT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_scene_project_id` (`project_id`),
    KEY `ix_ai_scene_name` (`name`),
    KEY `ix_ai_scene_status` (`status`),
    KEY `ix_ai_scene_created_by` (`created_by`),
    CONSTRAINT `fk_ai_scene_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_scene_reference_file_id`
        FOREIGN KEY (`reference_file_id`) REFERENCES `ai_file` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_scene_prompt_id`
        FOREIGN KEY (`prompt_id`) REFERENCES `ai_prompt` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_scene_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_script` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NOT NULL,
    `title` VARCHAR(200) NOT NULL,
    `summary` TEXT NULL,
    `content` TEXT NOT NULL,
    `duration` INT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_script_project_id` (`project_id`),
    KEY `ix_ai_script_title` (`title`),
    KEY `ix_ai_script_status` (`status`),
    KEY `ix_ai_script_created_by` (`created_by`),
    CONSTRAINT `fk_ai_script_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_script_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_storyboard` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `script_id` BIGINT NOT NULL,
    `project_id` BIGINT NOT NULL,
    `sequence` INT NOT NULL DEFAULT 1,
    `title` VARCHAR(200) NOT NULL,
    `description` TEXT NULL,
    `duration` FLOAT NULL,
    `camera` VARCHAR(200) NULL,
    `dialogue` TEXT NULL,
    `video_prompt` TEXT NULL,
    `scene_id` BIGINT NULL,
    `character_ids` JSON NOT NULL,
    `reference_file_ids` JSON NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_storyboard_script_id` (`script_id`),
    KEY `ix_ai_storyboard_project_id` (`project_id`),
    KEY `ix_ai_storyboard_status` (`status`),
    KEY `ix_ai_storyboard_created_by` (`created_by`),
    CONSTRAINT `fk_ai_storyboard_script_id`
        FOREIGN KEY (`script_id`) REFERENCES `ai_script` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_storyboard_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_storyboard_scene_id`
        FOREIGN KEY (`scene_id`) REFERENCES `ai_scene` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_storyboard_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_task` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT NULL,
    `name` VARCHAR(200) NOT NULL,
    `task_type` VARCHAR(30) NOT NULL,
    `target_type` VARCHAR(30) NULL,
    `target_id` BIGINT NULL,
    `model_config_id` BIGINT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    `progress` INT NOT NULL DEFAULT 0,
    `request_payload` JSON NOT NULL,
    `result_payload` JSON NOT NULL,
    `error_message` TEXT NULL,
    `started_at` DATETIME NULL,
    `finished_at` DATETIME NULL,
    `created_by` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `ix_ai_task_project_id` (`project_id`),
    KEY `ix_ai_task_name` (`name`),
    KEY `ix_ai_task_task_type` (`task_type`),
    KEY `ix_ai_task_status` (`status`),
    KEY `ix_ai_task_created_by` (`created_by`),
    CONSTRAINT `fk_ai_task_project_id`
        FOREIGN KEY (`project_id`) REFERENCES `ai_project` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_task_model_config_id`
        FOREIGN KEY (`model_config_id`) REFERENCES `ai_model_config` (`id`)
        ON DELETE SET NULL ON UPDATE RESTRICT,
    CONSTRAINT `fk_ai_task_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `alembic_version` (
    `version_num` VARCHAR(32) NOT NULL,
    PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `sys_user` (`username`, `password_hash`, `nickname`, `status`)
VALUES (
    'admin',
    '$2b$12$RkPTa9O/8nK0b4/8KBiyHuF9IksQEpzb6Sl1MHl3isZA5SLDH9Z52',
    '系统管理员',
    'ENABLED'
)
ON DUPLICATE KEY UPDATE `username` = VALUES(`username`);

INSERT INTO `alembic_version` (`version_num`)
SELECT '20260929_0004'
WHERE NOT EXISTS (SELECT 1 FROM `alembic_version`);

UPDATE `alembic_version`
SET `version_num` = '20260929_0004'
WHERE `version_num` IN ('20260929_0001', '20260929_0002', '20260929_0003');

