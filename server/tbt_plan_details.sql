USE [Count_Stock]
GO

/****** Object:  Table [dbo].[tbt_plan_details]    Script Date: 06/08/2026 16:06:25 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[tbt_plan_details](
	[plan_detail_id] [int] IDENTITY(1,1) NOT NULL,
	[plan_id] [int] NOT NULL,
	[item_id] [int] NOT NULL,
	[new_zone] [nvarchar](500) NULL,
	[before_zone] [nvarchar](500) NULL,
	[new_location] [nvarchar](500) NULL,
	[before_location] [nvarchar](500) NULL,
	[qty] [numeric](18, 2) NULL,
	[qty_on_hand] [numeric](18, 2) NULL,
	[qty_audit] [numeric](18, 2) NULL,
	[check_date] [datetime] NULL,
	[checker] [nvarchar](500) NULL,
	[auditor] [nvarchar](500) NULL,
	[status_id] [int] NULL,
	[remark] [nvarchar](1000) NULL,
	[barcode] [nvarchar](100) NULL,
	[udf1] [nvarchar](1000) NULL,
	[udf2] [nvarchar](1000) NULL,
	[udf3] [nvarchar](1000) NULL,
	[audit_count] [int] NULL,
	[create_date] [datetime] NULL,
	[create_by] [int] NULL,
	[update_date] [datetime] NULL,
	[update_by] [int] NULL,
	[is_confirm] [bit] NOT NULL,
	[is_change_location] [bit] NOT NULL,
	[is_check] [bit] NOT NULL,
 CONSTRAINT [PK_tbt_plan_details_1] PRIMARY KEY CLUSTERED 
(
	[plan_detail_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_qty]  DEFAULT ((0)) FOR [qty]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_qty_on_hand]  DEFAULT ((0)) FOR [qty_on_hand]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_qty_audit]  DEFAULT ((0)) FOR [qty_audit]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_audit_count]  DEFAULT ((0)) FOR [audit_count]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_create_date]  DEFAULT (getdate()) FOR [create_date]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_is_confirm]  DEFAULT ((0)) FOR [is_confirm]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_is_change_location]  DEFAULT ((0)) FOR [is_change_location]
GO

ALTER TABLE [dbo].[tbt_plan_details] ADD  CONSTRAINT [DF_tbt_plan_details_is_check]  DEFAULT ((0)) FOR [is_check]
GO

ALTER TABLE [dbo].[tbt_plan_details]  WITH CHECK ADD  CONSTRAINT [FK_tbt_plan_details_tbt_plan_assets] FOREIGN KEY([plan_id])
REFERENCES [dbo].[tbt_plans] ([plan_id])
GO

ALTER TABLE [dbo].[tbt_plan_details] CHECK CONSTRAINT [FK_tbt_plan_details_tbt_plan_assets]
GO


