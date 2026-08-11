USE [Count_Stock]
GO

/****** Object:  Table [dbo].[tbt_sync_count_staging]    Script Date: 06/08/2026 16:07:32 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[tbt_sync_count_staging](
	[staging_id] [bigint] IDENTITY(1,1) NOT NULL,
	[transaction_guid] [uniqueidentifier] NOT NULL,
	[reference_transaction_guid] [uniqueidentifier] NULL,
	[transaction_no] [nvarchar](100) NULL,
	[device_id] [uniqueidentifier] NOT NULL,
	[device_name] [nvarchar](100) NULL,
	[app_version] [nvarchar](50) NULL,
	[plan_id] [int] NOT NULL,
	[plan_detail_id] [int] NOT NULL,
	[item_id] [int] NOT NULL,
	[location_id] [int] NULL,
	[location_code] [nvarchar](100) NULL,
	[barcode] [nvarchar](100) NULL,
	[qty] [decimal](18, 2) NOT NULL,
	[checker] [nvarchar](500) NULL,
	[transaction_type] [varchar](20) NOT NULL,
	[operation_type] [varchar](30) NOT NULL,
	[audit_round] [int] NOT NULL,
	[transaction_date] [datetime2](0) NULL,
	[received_at] [datetime2](0) NOT NULL,
	[process_status] [varchar](20) NOT NULL,
	[process_batch_id] [uniqueidentifier] NULL,
	[process_by_device_id] [uniqueidentifier] NULL,
	[process_started_at] [datetime2](0) NULL,
	[processed_at] [datetime2](0) NULL,
	[retry_count] [int] NOT NULL,
	[target_history_id] [int] NULL,
	[error_code] [varchar](100) NULL,
	[error_message] [nvarchar](1000) NULL,
	[sync_batch_guid] [uniqueidentifier] NULL,
 CONSTRAINT [PK_tbt_sync_count_staging] PRIMARY KEY CLUSTERED 
(
	[staging_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] ADD  CONSTRAINT [DF_sync_count_audit_round]  DEFAULT ((0)) FOR [audit_round]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] ADD  CONSTRAINT [DF_sync_count_received_at]  DEFAULT (sysdatetime()) FOR [received_at]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] ADD  CONSTRAINT [DF_sync_count_process_status]  DEFAULT ('WAITING') FOR [process_status]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] ADD  CONSTRAINT [DF_sync_count_retry_count]  DEFAULT ((0)) FOR [retry_count]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging]  WITH CHECK ADD  CONSTRAINT [CK_sync_count_operation_type] CHECK  (([operation_type]='UPDATE_LOCATION' OR [operation_type]='UPDATE_QTY' OR [operation_type]='INSERT'))
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] CHECK CONSTRAINT [CK_sync_count_operation_type]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging]  WITH CHECK ADD  CONSTRAINT [CK_sync_count_process_status] CHECK  (([process_status]='ERROR' OR [process_status]='SUCCESS' OR [process_status]='PROCESSING' OR [process_status]='WAITING'))
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] CHECK CONSTRAINT [CK_sync_count_process_status]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging]  WITH CHECK ADD  CONSTRAINT [CK_sync_count_qty] CHECK  (([qty]>=(0)))
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] CHECK CONSTRAINT [CK_sync_count_qty]
GO

ALTER TABLE [dbo].[tbt_sync_count_staging]  WITH CHECK ADD  CONSTRAINT [CK_sync_count_transaction_type] CHECK  (([transaction_type]='AUDIT' OR [transaction_type]='COUNT'))
GO

ALTER TABLE [dbo].[tbt_sync_count_staging] CHECK CONSTRAINT [CK_sync_count_transaction_type]
GO


