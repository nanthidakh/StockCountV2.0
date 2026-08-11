<%@ WebHandler Language="C#" Class="SyncCountHandler" %>

using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Web;
using System.Web.Script.Serialization;

public class SyncCountHandler : IHttpHandler
{
    private sealed class SyncRequest
    {
        public string device_id { get; set; }
        public string device_name { get; set; }
        public string app_version { get; set; }
        public string sync_batch_guid { get; set; }
        public List<SyncTransaction> transactions { get; set; }
    }

    private sealed class SyncTransaction
    {
        public string transaction_guid { get; set; }
        public string reference_transaction_guid { get; set; }
        public string transaction_no { get; set; }
        public string transaction_type { get; set; }
        public string operation_type { get; set; }
        public int plan_id { get; set; }
        public int plan_detail_id { get; set; }
        public int item_id { get; set; }
        public int? location_id { get; set; }
        public string location_code { get; set; }
        public string barcode { get; set; }
        public decimal qty { get; set; }
        public string checker { get; set; }
        public int audit_round { get; set; }
        public string transaction_date { get; set; }
    }

    public void ProcessRequest(HttpContext context)
    {
        JsonResponseHelper.Prepare(context);

        var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue, RecursionLimit = 100 };

        try
        {
            if (!String.Equals(context.Request.HttpMethod, "POST", StringComparison.OrdinalIgnoreCase))
            {
                WriteJson(context, json, new { success = false, message = "POST only" }, 405);
                return;
            }

            string body;
            using (var reader = new StreamReader(context.Request.InputStream))
                body = reader.ReadToEnd();

            SyncRequest request = json.Deserialize<SyncRequest>(body);
            if (request == null) throw new ApplicationException("Invalid JSON request.");

            Guid deviceId;
            if (!Guid.TryParse(request.device_id, out deviceId))
                throw new ApplicationException("device_id is required and must be UUID.");

            Guid syncBatchGuid;
            if (!Guid.TryParse(request.sync_batch_guid, out syncBatchGuid))
                throw new ApplicationException("sync_batch_guid is required and must be UUID.");

            if (request.transactions == null) request.transactions = new List<SyncTransaction>();

            var results = new List<object>();
            int inserted = 0, duplicate = 0, error = 0;

            using (var connection = new SqlConnection(GetConnectionString()))
            {
                connection.Open();

                foreach (SyncTransaction item in request.transactions)
                {
                    Guid transactionGuid;
                    if (item == null || !Guid.TryParse(item.transaction_guid, out transactionGuid))
                    {
                        error++;
                        results.Add(new { transaction_guid = item == null ? null : item.transaction_guid, success = false, server_status = "ERROR", message = "Invalid transaction_guid" });
                        continue;
                    }

                    try
                    {
                        string transactionType;
                        string operationType;
                        NormalizeTypes(item.transaction_type, item.operation_type, out transactionType, out operationType);

                        Guid referenceGuid;
                        object referenceValue = Guid.TryParse(item.reference_transaction_guid, out referenceGuid) ? (object)referenceGuid : DBNull.Value;

                        DateTime transactionDate;
                        object dateValue = DateTime.TryParse(item.transaction_date, out transactionDate) ? (object)transactionDate : DBNull.Value;

                        using (var command = new SqlCommand(@"
IF EXISTS (SELECT 1 FROM dbo.tbt_sync_count_staging WITH (UPDLOCK,HOLDLOCK) WHERE transaction_guid=@transaction_guid)
    SELECT CAST(0 AS bit);
ELSE
BEGIN
    INSERT INTO dbo.tbt_sync_count_staging
    (
        transaction_guid, reference_transaction_guid, transaction_no, sync_batch_guid,
        device_id, device_name, app_version,
        plan_id, plan_detail_id, item_id,
        location_id, location_code, barcode, qty, checker,
        transaction_type, operation_type, audit_round,
        transaction_date, process_status
    )
    VALUES
    (
        @transaction_guid, @reference_transaction_guid, @transaction_no, @sync_batch_guid,
        @device_id, @device_name, @app_version,
        @plan_id, @plan_detail_id, @item_id,
        @location_id, @location_code, @barcode, @qty, @checker,
        @transaction_type, @operation_type, @audit_round,
        @transaction_date, 'WAITING'
    );
    SELECT CAST(1 AS bit);
END", connection))
                        {
                            command.Parameters.Add("@transaction_guid", SqlDbType.UniqueIdentifier).Value = transactionGuid;
                            command.Parameters.Add("@reference_transaction_guid", SqlDbType.UniqueIdentifier).Value = referenceValue;
                            command.Parameters.Add("@transaction_no", SqlDbType.NVarChar, 100).Value = Db(item.transaction_no);
                            command.Parameters.Add("@sync_batch_guid", SqlDbType.UniqueIdentifier).Value = syncBatchGuid;
                            command.Parameters.Add("@device_id", SqlDbType.UniqueIdentifier).Value = deviceId;
                            command.Parameters.Add("@device_name", SqlDbType.NVarChar, 100).Value = Db(request.device_name);
                            command.Parameters.Add("@app_version", SqlDbType.NVarChar, 50).Value = Db(request.app_version);
                            command.Parameters.Add("@plan_id", SqlDbType.Int).Value = item.plan_id;
                            command.Parameters.Add("@plan_detail_id", SqlDbType.Int).Value = item.plan_detail_id;
                            command.Parameters.Add("@item_id", SqlDbType.Int).Value = item.item_id;
                            command.Parameters.Add("@location_id", SqlDbType.Int).Value = Db(item.location_id);
                            command.Parameters.Add("@location_code", SqlDbType.NVarChar, 100).Value = Db(item.location_code);
                            command.Parameters.Add("@barcode", SqlDbType.NVarChar, 100).Value = Db(item.barcode);
                            SqlParameter qty = command.Parameters.Add("@qty", SqlDbType.Decimal);
                            qty.Precision = 18; qty.Scale = 2; qty.Value = item.qty;
                            command.Parameters.Add("@checker", SqlDbType.NVarChar, 500).Value = Db(item.checker);
                            command.Parameters.Add("@transaction_type", SqlDbType.VarChar, 20).Value = transactionType;
                            command.Parameters.Add("@operation_type", SqlDbType.VarChar, 30).Value = operationType;
                            command.Parameters.Add("@audit_round", SqlDbType.Int).Value = item.audit_round < 0 ? 0 : item.audit_round;
                            command.Parameters.Add("@transaction_date", SqlDbType.DateTime2).Value = dateValue;

                            bool added = Convert.ToBoolean(command.ExecuteScalar());
                            if (added)
                            {
                                inserted++;
                                results.Add(new { transaction_guid = transactionGuid, success = true, server_status = "WAITING", message = "Received" });
                            }
                            else
                            {
                                duplicate++;
                                results.Add(new { transaction_guid = transactionGuid, success = true, server_status = "DUPLICATE", message = "Already received" });
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        error++;
                        results.Add(new { transaction_guid = item.transaction_guid, success = false, server_status = "ERROR", message = ex.Message });
                    }
                }
            }

            WriteJson(context, json, new
            {
                success = error == 0,
                received = request.transactions.Count,
                inserted = inserted,
                duplicate = duplicate,
                error = error,
                device_id = deviceId,
                sync_batch_guid = syncBatchGuid,
                results = results
            }, 200);
        }
        catch (Exception ex)
        {
            WriteJson(context, json, new { success = false, message = ex.Message }, 500);
        }
    }

    private static void NormalizeTypes(string sourceType, string sourceOperation, out string transactionType, out string operationType)
    {
        string type = (sourceType ?? "COUNT").Trim().ToUpperInvariant();
        string operation = (sourceOperation ?? "").Trim().ToUpperInvariant();

        if (type == "CORRECTION_QTY") { type = "COUNT"; operation = "UPDATE_QTY"; }
        else if (type == "CORRECTION_LOCATION") { type = "COUNT"; operation = "UPDATE_LOCATION"; }

        if (type != "COUNT" && type != "AUDIT") throw new ApplicationException("Unsupported transaction_type: " + type);
        if (String.IsNullOrEmpty(operation)) operation = "INSERT";
        if (operation != "INSERT" && operation != "UPDATE_QTY" && operation != "UPDATE_LOCATION")
            throw new ApplicationException("Unsupported operation_type: " + operation);

        transactionType = type;
        operationType = operation;
    }

    private static object Db(object value)
    {
        if (value == null) return DBNull.Value;
        string text = value as string;
        if (text != null && String.IsNullOrWhiteSpace(text)) return DBNull.Value;
        return value;
    }

    private static string GetConnectionString()
    {
        string value = ConfigurationManager.AppSettings["strConn"];

        if (String.IsNullOrWhiteSpace(value))
        {
            throw new ConfigurationErrorsException(
                "Missing appSettings key: strConn in Web.config."
            );
        }

        return value.Trim();
    }

    private static void WriteJson(HttpContext context, JavaScriptSerializer json, object value, int statusCode)
    {
        JsonResponseHelper.Write(context, json, value, statusCode);
    }

    public bool IsReusable { get { return false; } }
}
