<%@ WebHandler Language="C#" Class="GetConfigHandler" %>

using System;
using System.Web;
using System.Web.Script.Serialization;

public class GetConfigHandler : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        context.Response.Clear();
        context.Response.ContentType = "application/json";
        context.Response.ContentEncoding =
            System.Text.Encoding.UTF8;

        context.Response.Cache.SetCacheability(
            HttpCacheability.NoCache
        );

        context.Response.Cache.SetNoStore();

        string host = context.Request.Url.Host;
        int port = context.Request.Url.Port;
        string scheme = context.Request.Url.Scheme;

        string root;

        if (port == 80 || port == 443)
        {
            root =
                scheme +
                "://" +
                host +
                "/countstock";
        }
        else
        {
            root =
                scheme +
                "://" +
                host +
                ":" +
                port +
                "/countstock";
        }

        var config = new
        {
            success = true,

            api_url =
                root + "/app_api",

            download_url =
                root + "/app_api/DownloadPlan.ashx",

            sync_url =
                root + "/app_api/SyncCount.ashx",

            login_url =
                root + "/app_api/Login.ashx",

            sync_batch = 500,

            timeout = 120
        };

        JavaScriptSerializer serializer =
            new JavaScriptSerializer();

        context.Response.StatusCode = 200;
        context.Response.TrySkipIisCustomErrors = true;

        context.Response.Write(
            serializer.Serialize(config)
        );
    }

    public bool IsReusable
    {
        get
        {
            return false;
        }
    }
}