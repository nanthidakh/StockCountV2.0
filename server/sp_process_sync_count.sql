USE [Count_Stock]
GO

/****** Object:  StoredProcedure [dbo].[sp_process_sync_count]    Script Date: 11/08/2026 14:14:22 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO






/*
=========================================================
Project   : HWK_StockV1
Procedure : dbo.sp_process_sync_count
Purpose   : Process งานของ Device + Plan ที่กดเท่านั้น
Mode      : Atomic ทั้งชุด
Important : ไม่ ALTER dbo.tbt_count_history
=========================================================
*/

ALTER   PROCEDURE [dbo].[sp_process_sync_count]
(
    @DeviceID UNIQUEIDENTIFIER,
    @PlanID INT,
    @SyncBatchGUID UNIQUEIDENTIFIER,
    @ProcessBy NVARCHAR(100) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @DeviceID IS NULL
        THROW 50001, 'DeviceID is required.', 1;

    IF @PlanID IS NULL OR @PlanID <= 0
        THROW 50002, 'PlanID is required.', 1;

    IF @SyncBatchGUID IS NULL
        THROW 50003, 'SyncBatchGUID is required.', 1;

    DECLARE @BatchID UNIQUEIDENTIFIER = NEWID();
    DECLARE @Selected INT = 0;
    DECLARE @ErrorCount INT = 0;
    DECLARE @Now DATETIME2(0) = SYSDATETIME();

    CREATE TABLE #Work
    (
        staging_id BIGINT NOT NULL PRIMARY KEY,
        transaction_guid UNIQUEIDENTIFIER NOT NULL,
        reference_transaction_guid UNIQUEIDENTIFIER NULL,
        plan_detail_id INT NOT NULL,
        item_id INT NOT NULL,
        location_id INT NULL,
        location_code NVARCHAR(100) NULL,
        barcode NVARCHAR(100) NULL,
        qty DECIMAL(18,2) NOT NULL,
        checker NVARCHAR(500) NULL,
        transaction_type VARCHAR(20) NOT NULL,
        operation_type VARCHAR(30) NOT NULL,
        audit_round INT NOT NULL,
        transaction_date DATETIME2(0) NULL,
        target_history_id INT NULL,
        validation_error_code VARCHAR(100) NULL,
        validation_error_message NVARCHAR(1000) NULL
    );

    /* Claim งานทั้งหมดของเครื่องและ Plan นี้ */
    BEGIN TRANSACTION;

    INSERT INTO #Work
    (
        staging_id,
        transaction_guid,
        reference_transaction_guid,
        plan_detail_id,
        item_id,
        location_id,
        location_code,
        barcode,
        qty,
        checker,
        transaction_type,
        operation_type,
        audit_round,
        transaction_date,
        target_history_id
    )
    SELECT
        s.staging_id,
        s.transaction_guid,
        s.reference_transaction_guid,
        s.plan_detail_id,
        s.item_id,
        s.location_id,
        s.location_code,
        s.barcode,
        s.qty,
        s.checker,
        s.transaction_type,
        s.operation_type,
        s.audit_round,
        s.transaction_date,
        s.target_history_id
    FROM dbo.tbt_sync_count_staging s WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE s.device_id = @DeviceID
      AND s.plan_id = @PlanID
      AND s.sync_batch_guid = @SyncBatchGUID
      AND s.process_status = 'WAITING';

    SET @Selected = @@ROWCOUNT;

    UPDATE s
    SET
        s.process_status = 'PROCESSING',
        s.process_batch_id = @BatchID,
        s.process_by_device_id = @DeviceID,
        s.process_started_at = @Now,
        s.processed_at = NULL,
        s.error_code = NULL,
        s.error_message = NULL
    FROM dbo.tbt_sync_count_staging s
    INNER JOIN #Work w
        ON w.staging_id = s.staging_id;

    COMMIT TRANSACTION;

    IF @Selected = 0
    BEGIN
        SELECT
            CAST(1 AS bit) AS success,
            CONVERT(VARCHAR(36), @BatchID) AS batch_id,
            0 AS selected,
            0 AS processed,
            0 AS error,
            N'ไม่มีข้อมูลของเครื่องนี้ที่รอ Process' AS message;
        RETURN;
    END;

    /* =====================================================
       Validation: ถ้ามี Error แม้แต่ 1 รายการ จะไม่ลงตารางจริง
       ===================================================== */

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.tbt_plans
        WHERE plan_id = @PlanID
    )
    BEGIN
        UPDATE #Work
        SET
            validation_error_code = 'PLAN_NOT_FOUND',
            validation_error_message = N'ไม่พบ Plan';
    END;

    /* Local Plan Detail: plan_detail_id <= 0 means Android confirmed a new item/location pair.
       No server schema change is required. The existing sp_insert_plan_detail is reused. */
    DECLARE @NewStagingID BIGINT, @NewItemID INT, @NewLocationID INT,
            @NewLocationCode NVARCHAR(100), @RealPlanDetailID INT, @LocationName NVARCHAR(256);

    DECLARE new_detail_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT staging_id, item_id, location_id, location_code
        FROM #Work
        WHERE operation_type = 'INSERT' AND plan_detail_id <= 0;

    OPEN new_detail_cursor;
    FETCH NEXT FROM new_detail_cursor INTO @NewStagingID,@NewItemID,@NewLocationID,@NewLocationCode;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @RealPlanDetailID = NULL;
        SET @LocationName = NULL;

        SELECT @NewLocationCode = l.location_code, @LocationName = l.location_name
        FROM dbo.tbm_locations l
        WHERE l.location_id=@NewLocationID AND l.is_active=1;

        IF @LocationName IS NOT NULL
        BEGIN
            /* Retry-safe: use an existing Plan Detail first. */
            SELECT TOP (1) @RealPlanDetailID=pd.plan_detail_id
            FROM dbo.tbt_plan_details pd
            WHERE pd.plan_id=@PlanID AND pd.item_id=@NewItemID
              AND (LTRIM(RTRIM(ISNULL(pd.new_location,'')))=LTRIM(RTRIM(@LocationName))
                   OR LTRIM(RTRIM(ISNULL(pd.before_location,'')))=LTRIM(RTRIM(@LocationName)))
            ORDER BY pd.plan_detail_id DESC;

            IF @RealPlanDetailID IS NULL
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM dbo.tbm_item_location WHERE item_id=@NewItemID AND location_id=@NewLocationID)
                    INSERT INTO dbo.tbm_item_location(item_id,location_id,create_date,create_by)
                    VALUES(@NewItemID,@NewLocationID,GETDATE(),10);

                EXEC dbo.sp_insert_plan_detail @plan_id=@PlanID, @item_id=@NewItemID,
                     @location_code=@NewLocationCode, @user_id=10;

                SELECT TOP (1) @RealPlanDetailID=pd.plan_detail_id
                FROM dbo.tbt_plan_details pd
                WHERE pd.plan_id=@PlanID AND pd.item_id=@NewItemID
                  AND (LTRIM(RTRIM(ISNULL(pd.new_location,'')))=LTRIM(RTRIM(@LocationName))
                       OR LTRIM(RTRIM(ISNULL(pd.before_location,'')))=LTRIM(RTRIM(@LocationName)))
                ORDER BY pd.plan_detail_id DESC;
            END;
        END;

        IF @RealPlanDetailID IS NULL
        BEGIN
            UPDATE #Work SET validation_error_code='CREATE_PLAN_DETAIL_FAILED',
                validation_error_message=N'ไม่สามารถสร้าง Plan Detail สำหรับ Location ใหม่ได้'
            WHERE staging_id=@NewStagingID;
        END
        ELSE
        BEGIN
            UPDATE #Work SET plan_detail_id=@RealPlanDetailID, location_code=@NewLocationCode
            WHERE staging_id=@NewStagingID;
            UPDATE dbo.tbt_sync_count_staging SET plan_detail_id=@RealPlanDetailID, location_code=@NewLocationCode
            WHERE staging_id=@NewStagingID;
        END;

        FETCH NEXT FROM new_detail_cursor INTO @NewStagingID,@NewItemID,@NewLocationID,@NewLocationCode;
    END;
    CLOSE new_detail_cursor; DEALLOCATE new_detail_cursor;

    UPDATE w
    SET
        validation_error_code = 'PLAN_DETAIL_MISMATCH',
        validation_error_message = N'Plan Detail, Plan หรือ Item ไม่ตรงกัน'
    FROM #Work w
    WHERE w.validation_error_code IS NULL
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.tbt_plan_details pd
          WHERE pd.plan_detail_id = w.plan_detail_id
            AND pd.plan_id = @PlanID
            AND pd.item_id = w.item_id
      );

    UPDATE w
    SET
        validation_error_code = 'ITEM_NOT_FOUND',
        validation_error_message = N'ไม่พบสินค้า หรือสินค้าถูกยกเลิก'
    FROM #Work w
    WHERE w.validation_error_code IS NULL
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.tbm_stock_item i
          WHERE i.item_id = w.item_id
            AND ISNULL(i.is_active, 1) = 1
      );

    UPDATE #Work
    SET
        validation_error_code = 'INVALID_QTY',
        validation_error_message = N'จำนวนต้องไม่ติดลบ'
    WHERE validation_error_code IS NULL
      AND qty < 0;

    /* Resolve location_code -> location_id */
    UPDATE w
    SET
        w.location_id = l.location_id,
        w.location_code = l.location_code
    FROM #Work w
    INNER JOIN dbo.tbm_locations l
        ON l.location_code = w.location_code
       AND l.is_active = 1
    WHERE w.location_id IS NULL
      AND NULLIF(LTRIM(RTRIM(w.location_code)), N'') IS NOT NULL;

    UPDATE w
    SET
        validation_error_code = 'LOCATION_NOT_FOUND',
        validation_error_message = N'ไม่พบ Location ที่ใช้งานอยู่'
    FROM #Work w
    WHERE w.validation_error_code IS NULL
      AND
      (
          w.location_id IS NULL
          OR NOT EXISTS
          (
              SELECT 1
              FROM dbo.tbm_locations l
              WHERE l.location_id = w.location_id
                AND l.is_active = 1
          )
      );

    UPDATE w
    SET w.location_code = l.location_code
    FROM #Work w
    INNER JOIN dbo.tbm_locations l
        ON l.location_id = w.location_id
    WHERE w.validation_error_code IS NULL;

    /* Correction ต้องอ้างอิง Transaction ต้นทางใน Staging */
    UPDATE w
    SET
        validation_error_code = 'REFERENCE_REQUIRED',
        validation_error_message = N'Correction ต้องระบุ reference_transaction_guid'
    FROM #Work w
    WHERE w.validation_error_code IS NULL
      AND w.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
      AND w.reference_transaction_guid IS NULL;

    /* Resolve target_history_id จาก Transaction ต้นทางที่ Process สำเร็จแล้ว */
    UPDATE w
    SET w.target_history_id = original.target_history_id
    FROM #Work w
    INNER JOIN dbo.tbt_sync_count_staging original
        ON original.transaction_guid = w.reference_transaction_guid
       AND original.device_id = @DeviceID
       AND original.plan_id = @PlanID
       AND original.plan_detail_id = w.plan_detail_id
       AND original.item_id = w.item_id
       AND original.process_status = 'SUCCESS'
       AND original.target_history_id IS NOT NULL
    WHERE w.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
      AND w.target_history_id IS NULL;

    /* รองรับต้นทาง INSERT ที่อยู่ใน Batch เดียวกัน */
    UPDATE w
    SET w.target_history_id = -original.staging_id
    FROM #Work w
    INNER JOIN #Work original
        ON original.transaction_guid = w.reference_transaction_guid
       AND original.plan_detail_id = w.plan_detail_id
       AND original.item_id = w.item_id
       AND original.operation_type = 'INSERT'
    WHERE w.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
      AND w.validation_error_code IS NULL
      AND w.target_history_id IS NULL;

    UPDATE w
    SET
        validation_error_code = 'REFERENCE_NOT_FOUND',
        validation_error_message = N'ไม่พบ Transaction ต้นทางของเครื่องนี้'
    FROM #Work w
    WHERE w.validation_error_code IS NULL
      AND w.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
      AND w.target_history_id IS NULL;

    /* Correction ต้องอ้าง History ประเภทเดียวกับ Transaction
       ป้องกัน AUDIT UPDATE_QTY ไปแก้ qty_on_hand ของ COUNT และกลับกัน */
    UPDATE w
    SET
        validation_error_code = 'REFERENCE_TYPE_MISMATCH',
        validation_error_message = N'Transaction ต้นทางเป็นคนละประเภทกับรายการแก้ไข'
    FROM #Work w
    INNER JOIN dbo.tbt_count_history h
        ON h.history_id = w.target_history_id
    WHERE w.validation_error_code IS NULL
      AND w.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
      AND (
            (w.transaction_type = 'COUNT' AND ISNULL(h.is_audit, 0) <> 0)
         OR (w.transaction_type = 'AUDIT' AND ISNULL(h.is_audit, 0) <> 1)
      );

    /* Audit ต้องมี audit_round */
    UPDATE #Work
    SET
        validation_error_code = 'INVALID_AUDIT_ROUND',
        validation_error_message = N'Audit Round ต้องมากกว่า 0'
    WHERE validation_error_code IS NULL
      AND transaction_type = 'AUDIT'
      AND audit_round <= 0;

    SELECT @ErrorCount = COUNT(*)
    FROM #Work
    WHERE validation_error_code IS NOT NULL;

    IF @ErrorCount > 0
    BEGIN
        BEGIN TRANSACTION;

        UPDATE s
        SET
            s.process_status = 'ERROR',
            s.processed_at = SYSDATETIME(),
            s.retry_count = s.retry_count + 1,
            s.error_code = COALESCE(w.validation_error_code, 'BATCH_VALIDATION_FAILED'),
            s.error_message =
                CASE
                    WHEN w.validation_error_code IS NOT NULL
                        THEN w.validation_error_message
                    ELSE N'Batch มีรายการ Validation ไม่ผ่าน จึงยกเลิกทั้งชุด'
                END
        FROM dbo.tbt_sync_count_staging s
        INNER JOIN #Work w
            ON w.staging_id = s.staging_id;

        COMMIT TRANSACTION;

        SELECT
            CAST(0 AS bit) AS success,
            CONVERT(VARCHAR(36), @BatchID) AS batch_id,
            @Selected AS selected,
            0 AS processed,
            @ErrorCount AS error,
            N'Validation ไม่ผ่าน จึงไม่ Process ข้อมูลทั้งชุด' AS message;

        SELECT
            staging_id,
            transaction_guid,
            validation_error_code AS error_code,
            validation_error_message AS error_message
        FROM #Work
        WHERE validation_error_code IS NOT NULL
        ORDER BY staging_id;

        RETURN;
    END;

    /* =====================================================
       Atomic Process: Insert/Correction/Update Plan ทั้งหมด
       ===================================================== */
    BEGIN TRY
        BEGIN TRANSACTION;

        CREATE TABLE #InsertedHistory
        (
            staging_id BIGINT NOT NULL PRIMARY KEY,
            history_id INT NOT NULL
        );

        /* INSERT Count/Audit ใหม่ลง History
           ใช้ MERGE ON 1=0 เพื่อ OUTPUT staging_id คู่กับ history_id */
        MERGE dbo.tbt_count_history AS target
        USING
        (
            SELECT
                w.staging_id,
                @PlanID AS plan_id,
                w.plan_detail_id,
                w.item_id,
                w.location_id,
                pd.qty AS qty_order,
                CASE WHEN w.transaction_type = 'COUNT' THEN w.qty ELSE NULL END AS qty_on_hand,
                CASE WHEN w.transaction_type = 'AUDIT' THEN w.qty ELSE NULL END AS qty_recheck,
                w.checker,
                CASE WHEN w.transaction_type = 'AUDIT' THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS is_audit,
                COALESCE(CAST(w.transaction_date AS DATETIME), GETDATE()) AS scan_date
            FROM #Work w
            INNER JOIN dbo.tbt_plan_details pd
                ON pd.plan_detail_id = w.plan_detail_id
            WHERE w.operation_type = 'INSERT'
        ) AS source
        ON 1 = 0
        WHEN NOT MATCHED THEN
            INSERT
            (
                plan_id,
                plan_detail_id,
                item_id,
                location_id,
                qty_order,
                qty_on_hand,
                qty_recheck,
                checker,
                is_audit,
                scan_date
            )
            VALUES
            (
                source.plan_id,
                source.plan_detail_id,
                source.item_id,
                source.location_id,
                source.qty_order,
                source.qty_on_hand,
                source.qty_recheck,
                source.checker,
                source.is_audit,
                source.scan_date
            )
        OUTPUT
            source.staging_id,
            inserted.history_id
        INTO #InsertedHistory(staging_id, history_id);

        /* ใส่ history_id กลับเข้า Work */
        UPDATE w
        SET w.target_history_id = ih.history_id
        FROM #Work w
        INNER JOIN #InsertedHistory ih
            ON ih.staging_id = w.staging_id;

        /* Resolve Correction ที่อ้างถึง INSERT ใน Batch เดียวกัน */
        UPDATE correction
        SET correction.target_history_id = original.target_history_id
        FROM #Work correction
        INNER JOIN #Work original
            ON original.staging_id = -correction.target_history_id
        WHERE correction.operation_type IN ('UPDATE_QTY', 'UPDATE_LOCATION')
          AND correction.target_history_id < 0;

        /* แก้จำนวนเฉพาะ History ต้นทาง */
        UPDATE h
        SET
            h.qty_on_hand =
                CASE WHEN ISNULL(h.is_audit, 0) = 0 THEN w.qty ELSE h.qty_on_hand END,
            h.qty_recheck =
                CASE WHEN ISNULL(h.is_audit, 0) = 1 THEN w.qty ELSE h.qty_recheck END,
            h.checker = w.checker,
            h.scan_date = COALESCE(CAST(w.transaction_date AS DATETIME), GETDATE())
        FROM dbo.tbt_count_history h
        INNER JOIN #Work w
            ON w.target_history_id = h.history_id
        WHERE w.operation_type = 'UPDATE_QTY'
          AND (
                (w.transaction_type = 'COUNT' AND ISNULL(h.is_audit, 0) = 0)
             OR (w.transaction_type = 'AUDIT' AND ISNULL(h.is_audit, 0) = 1)
          );

        /* แก้ Location เฉพาะ History ต้นทาง */
        UPDATE h
        SET
            h.location_id = w.location_id,
            h.checker = w.checker,
            h.scan_date = COALESCE(CAST(w.transaction_date AS DATETIME), GETDATE())
        FROM dbo.tbt_count_history h
        INNER JOIN #Work w
            ON w.target_history_id = h.history_id
        WHERE w.operation_type = 'UPDATE_LOCATION'
          AND (
                (w.transaction_type = 'COUNT' AND ISNULL(h.is_audit, 0) = 0)
             OR (w.transaction_type = 'AUDIT' AND ISNULL(h.is_audit, 0) = 1)
          );

        /* Update Plan Detail เฉพาะรายการที่ได้รับผลกระทบ */
        ;WITH Affected AS
        (
            SELECT DISTINCT plan_detail_id
            FROM #Work
            WHERE transaction_type = 'COUNT'
        ),
        CountTotal AS
        (
            SELECT
                h.plan_detail_id,
                SUM(ISNULL(h.qty_on_hand, 0)) AS total_qty_on_hand,
                MAX(h.scan_date) AS last_count_date
            FROM dbo.tbt_count_history h
            INNER JOIN Affected a
                ON a.plan_detail_id = h.plan_detail_id
            WHERE ISNULL(h.is_audit, 0) = 0
            GROUP BY h.plan_detail_id
        ),
        LastCount AS
        (
            SELECT
                h.plan_detail_id,
                h.checker,
                h.location_id,
                ROW_NUMBER() OVER
                (
                    PARTITION BY h.plan_detail_id
                    ORDER BY h.scan_date DESC, h.history_id DESC
                ) AS rn
            FROM dbo.tbt_count_history h
            INNER JOIN Affected a
                ON a.plan_detail_id = h.plan_detail_id
            WHERE ISNULL(h.is_audit, 0) = 0
        ),
        LastWorkBarcode AS
        (
            SELECT
                w.plan_detail_id,
                w.barcode,
                ROW_NUMBER() OVER
                (
                    PARTITION BY w.plan_detail_id
                    ORDER BY w.staging_id DESC
                ) AS rn
            FROM #Work w
            WHERE w.transaction_type = 'COUNT'
        )
        UPDATE pd
        SET
            pd.qty_on_hand = ISNULL(ct.total_qty_on_hand, 0),
            pd.check_date = ct.last_count_date,
            pd.checker = lc.checker,
            pd.status_id =
                CASE
                    WHEN wb.plan_detail_id IS NOT NULL THEN 34
                    ELSE pd.status_id
                END,
            pd.barcode =
                CASE
                    WHEN wb.plan_detail_id IS NOT NULL THEN wb.barcode
                    ELSE pd.barcode
                END,
            pd.new_location = loc.location_code,
            pd.is_change_location =
                CASE
                    WHEN NULLIF(pd.before_location, N'') IS NOT NULL
                     AND ISNULL(pd.before_location, N'') <> ISNULL(loc.location_code, N'')
                        THEN 1
                    ELSE pd.is_change_location
                END,
            pd.is_check = 1,
            pd.update_date = GETDATE()
        FROM dbo.tbt_plan_details pd
        INNER JOIN Affected a
            ON a.plan_detail_id = pd.plan_detail_id
        LEFT JOIN CountTotal ct
            ON ct.plan_detail_id = pd.plan_detail_id
        LEFT JOIN LastCount lc
            ON lc.plan_detail_id = pd.plan_detail_id
           AND lc.rn = 1
        LEFT JOIN LastWorkBarcode wb
            ON wb.plan_detail_id = pd.plan_detail_id
           AND wb.rn = 1
        LEFT JOIN dbo.tbm_locations loc
            ON loc.location_id = lc.location_id;

        /* Audit: ใช้ผล Audit ล่าสุดของแต่ละ Plan Detail
           ไม่ SUM ข้ามการ Audit หลายครั้ง
           เรียงตาม scan_date ล่าสุด และ history_id ล่าสุดเมื่อเวลาเท่ากัน */
        ;WITH Affected AS
        (
            SELECT DISTINCT plan_detail_id
            FROM #Work
            WHERE transaction_type = 'AUDIT'
        ),
        LatestRound AS
        (
            SELECT
                x.plan_detail_id,
                MAX(x.audit_round) AS audit_round
            FROM
            (
                SELECT s.plan_detail_id, s.audit_round
                FROM dbo.tbt_sync_count_staging s
                INNER JOIN Affected a
                    ON a.plan_detail_id = s.plan_detail_id
                WHERE s.transaction_type = 'AUDIT'
                  AND s.process_status = 'SUCCESS'

                UNION ALL

                SELECT w.plan_detail_id, w.audit_round
                FROM #Work w
                WHERE w.transaction_type = 'AUDIT'
            ) x
            GROUP BY x.plan_detail_id
        ),
        RoundHistory AS
        (
            SELECT DISTINCT
                s.plan_detail_id,
                s.target_history_id AS history_id
            FROM dbo.tbt_sync_count_staging s
            INNER JOIN LatestRound lr
                ON lr.plan_detail_id = s.plan_detail_id
               AND lr.audit_round = s.audit_round
            WHERE s.transaction_type = 'AUDIT'
              AND s.process_status = 'SUCCESS'
              AND s.target_history_id IS NOT NULL

            UNION

            SELECT DISTINCT
                w.plan_detail_id,
                w.target_history_id
            FROM #Work w
            INNER JOIN LatestRound lr
                ON lr.plan_detail_id = w.plan_detail_id
               AND lr.audit_round = w.audit_round
            WHERE w.transaction_type = 'AUDIT'
              AND w.target_history_id IS NOT NULL
              AND w.target_history_id > 0
        ),
        LatestAudit AS
        (
            SELECT
                rh.plan_detail_id,
                h.qty_recheck,
                h.checker,
                h.scan_date,
                h.history_id,
                ROW_NUMBER() OVER
                (
                    PARTITION BY rh.plan_detail_id
                    ORDER BY h.scan_date DESC, h.history_id DESC
                ) AS rn
            FROM RoundHistory rh
            INNER JOIN dbo.tbt_count_history h
                ON h.history_id = rh.history_id
               AND ISNULL(h.is_audit, 0) = 1
        )
        UPDATE pd
        SET
            pd.qty_audit = ISNULL(la.qty_recheck, 0),
            pd.auditor = la.checker,
            pd.audit_count = lr.audit_round,
            pd.update_date = GETDATE()
        FROM dbo.tbt_plan_details pd
        INNER JOIN Affected a
            ON a.plan_detail_id = pd.plan_detail_id
        INNER JOIN LatestRound lr
            ON lr.plan_detail_id = pd.plan_detail_id
        LEFT JOIN LatestAudit la
            ON la.plan_detail_id = pd.plan_detail_id
           AND la.rn = 1;

        /* Staging SUCCESS */
        UPDATE s
        SET
            s.process_status = 'SUCCESS',
            s.target_history_id = w.target_history_id,
            s.processed_at = SYSDATETIME(),
            s.error_code = NULL,
            s.error_message = NULL
        FROM dbo.tbt_sync_count_staging s
        INNER JOIN #Work w
            ON w.staging_id = s.staging_id;

        COMMIT TRANSACTION;

        SELECT
            CAST(1 AS bit) AS success,
            CONVERT(VARCHAR(36), @BatchID) AS batch_id,
            @Selected AS selected,
            @Selected AS processed,
            0 AS error,
            N'Process สำเร็จทั้งชุด' AS message;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @CatchMessage NVARCHAR(1000) = ERROR_MESSAGE();

        BEGIN TRANSACTION;

        UPDATE s
        SET
            s.process_status = 'ERROR',
            s.processed_at = SYSDATETIME(),
            s.retry_count = s.retry_count + 1,
            s.error_code = 'PROCESS_FAILED',
            s.error_message = @CatchMessage
        FROM dbo.tbt_sync_count_staging s
        INNER JOIN #Work w
            ON w.staging_id = s.staging_id;

        COMMIT TRANSACTION;

        SELECT
            CAST(0 AS bit) AS success,
            CONVERT(VARCHAR(36), @BatchID) AS batch_id,
            @Selected AS selected,
            0 AS processed,
            @Selected AS error,
            @CatchMessage AS message;
    END CATCH;
END




GO


