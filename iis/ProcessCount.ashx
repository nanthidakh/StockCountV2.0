<%@ WebHandler Language="C#" Class="ProcessCountHandler" %>

using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Web;
using System.Web.Script.Serialization;

public class ProcessCountHandler : IHttpHandler
{
    private sealed class RequestData
    {
        public string device_id { get; set; }
        public string device_name { get; set; }
        public int plan_id { get; set; }
        public string sync_batch_guid { get; set; }
    }

    public void ProcessRequest(HttpContext context)
    {
        JsonResponseHelper.Prepare(context);

        var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };

        try
        {
            string body;
            using (var reader = new StreamReader(context.Request.InputStream))
                body = reader.ReadToEnd();

            RequestData request = json.Deserialize<RequestData>(body);
            if (request == null)
                throw new ApplicationException("Invalid JSON request.");

            Guid deviceId;
            if (!Guid.TryParse(request.device_id, out deviceId))
                throw new ApplicationException("Invalid device_id.");

            if (request.plan_id <= 0)
                throw new ApplicationException("Invalid plan_id.");

            Guid syncBatchGuid;
            if (!Guid.TryParse(request.sync_batch_guid, out syncBatchGuid))
                throw new ApplicationException("Invalid sync_batch_guid.");

            Dictionary<string, object> procedureResult = null;
            var validationErrors = new List<Dictionary<string, object>>();

            using (var connection = new SqlConnection(GetConnectionString()))
            using (var command = new SqlCommand("dbo.sp_process_sync_count", connection))
            {
                command.CommandType = CommandType.StoredProcedure;
                command.CommandTimeout = 600;
                command.Parameters.Add("@DeviceID", SqlDbType.UniqueIdentifier).Value = deviceId;
                command.Parameters.Add("@PlanID", SqlDbType.Int).Value = request.plan_id;
                command.Parameters.Add("@SyncBatchGUID", SqlDbType.UniqueIdentifier).Value = syncBatchGuid;
                command.Parameters.Add("@ProcessBy", SqlDbType.NVarChar, 100).Value = Db(request.device_name);

                connection.Open();

                using (var dataReader = command.ExecuteReader())
                {
                    // Result set 1: สรุปผล Process
                    if (dataReader.Read())
                        procedureResult = ReadRow(dataReader);

                    // Result set 2: รายการ Validation ที่ไม่ผ่าน
                    if (dataReader.NextResult())
                    {
                        while (dataReader.Read())
                            validationErrors.Add(ReadRow(dataReader));
                    }
                }
            }

            if (procedureResult == null)
                throw new ApplicationException("Stored procedure returned no result.");

            bool success = ToBoolean(GetValue(procedureResult, "success"));
            int selected = ToInt32(GetValue(procedureResult, "selected"));
            int processed = ToInt32(GetValue(procedureResult, "processed"));
            int error = ToInt32(GetValue(procedureResult, "error"));
            string message = Convert.ToString(GetValue(procedureResult, "message") ?? "");
            string batchId = Convert.ToString(GetValue(procedureResult, "batch_id") ?? "");
            JsonResponseHelper.Write(context, json, new
            {
                success = success,
                device_id = deviceId.ToString(),
                device_name = request.device_name,
                plan_id = request.plan_id,
                sync_batch_guid = syncBatchGuid.ToString(),
                batch_id = batchId,
                selected = selected,
                processed = processed,
                error = error,
                message = message,
                validation_errors = validationErrors
            }, 200);
        }
        catch (SqlException ex)
        {
            JsonResponseHelper.Write(context, json, new
            {
                success = false,
                error_type = "SQL_ERROR",
                sql_number = ex.Number,
                message = ex.Message,
                validation_errors = new object[0]
            }, 200);
        }
        catch (Exception ex)
        {
            JsonResponseHelper.Write(context, json, new
            {
                success = false,
                error_type = ex.GetType().Name,
                message = ex.Message,
                validation_errors = new object[0]
            }, 200);
        }
    }

    private static Dictionary<string, object> ReadRow(SqlDataReader reader)
    {
        var row = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i < reader.FieldCount; i++)
            row[reader.GetName(i)] = reader.IsDBNull(i) ? null : reader.GetValue(i);
        return row;
    }

    private static object GetValue(Dictionary<string, object> row, string key)
    {
        object value;
        return row.TryGetValue(key, out value) ? value : null;
    }

    private static bool ToBoolean(object value)
    {
        if (value == null || value == DBNull.Value) return false;
        return Convert.ToBoolean(value);
    }

    private static int ToInt32(object value)
    {
        if (value == null || value == DBNull.Value) return 0;
        return Convert.ToInt32(value);
    }

    private static object Db(object value)
    {
        if (value == null) return DBNull.Value;
        string text = value as string;
        return text != null && String.IsNullOrWhiteSpace(text) ? DBNull.Value : value;
    }

    private static string GetConnectionString()
    {
        string value = ConfigurationManager.AppSettings["strConn"];
        if (String.IsNullOrWhiteSpace(value))
            throw new ConfigurationErrorsException("Missing appSettings key: strConn in Web.config.");
        return value.Trim();
    }

    public bool IsReusable { get { return false; } }
}
