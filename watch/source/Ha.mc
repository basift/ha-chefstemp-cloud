import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;

(:background)
module Ha {
    // Storage keys for the cached credentials.
    const K_URL = "cfg_url";
    const K_TOKEN = "cfg_token";

    function trim(s as String) as String {
        var a = 0;
        var b = s.length();
        while (a < b && s.substring(a, a + 1).equals(" ")) { a++; }
        while (b > a && s.substring(b - 1, b).equals(" ")) { b--; }
        return s.substring(a, b) as String;
    }

    // Credentials are entered on the phone (Garmin Connect -> app settings ->
    // Properties). The first non-empty value seen is cached in Storage, which
    // survives app updates, so an upgraded/reinstalled app keeps working without
    // re-entering anything. A later non-empty Property (changed on the phone)
    // refreshes the cache; an empty Property falls back to the cache.
    function cred(propKey as String, cacheKey as String) as String {
        var p = Application.Properties.getValue(propKey);
        if (p instanceof String) {
            p = trim(p);
            if ((p as String).length() > 0) {
                var c = Application.Storage.getValue(cacheKey);
                if (!(c instanceof String) || !(c as String).equals(p)) {
                    try {
                        Application.Storage.setValue(cacheKey, p);
                    } catch (e) {
                    }
                }
                return p as String;
            }
        }
        var cached = Application.Storage.getValue(cacheKey);
        return (cached instanceof String) ? cached as String : "";
    }

    function baseUrl() as String {
        var u = cred("haUrl", K_URL);
        while (u.length() > 0 && u.substring(u.length() - 1, u.length()).equals("/")) {
            u = u.substring(0, u.length() - 1) as String;
        }
        return u;
    }

    function token() as String {
        return cred("haToken", K_TOKEN);
    }

    // True once both a URL and a token are known (from the phone or the cache).
    function configured() as Boolean {
        return baseUrl().length() > 0 && token().length() > 0;
    }

    function headers() as Dictionary {
        return {
            "Authorization" => "Bearer " + token(),
            "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON
        };
    }

    // Callback receives (responseCode, data) where data is the raw "a|b|c" template string.
    function fetchState(cb as Method) as Void {
        Communications.makeWebRequest(
            baseUrl() + "/api/template",
            { "template" => Ct.template() },
            {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :headers => headers(),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_TEXT_PLAIN
            },
            cb
        );
    }

    // service is e.g. "turn_on"; the domain is taken from the entity id.
    function callService(entityId as String, service as String, cb as Method) as Void {
        callServiceData(entityId, service, {}, cb);
    }

    // Like callService but merges extra service data (e.g. a timer duration).
    function callServiceData(entityId as String, service as String, data as Dictionary, cb as Method) as Void {
        var domain = entityId.substring(0, entityId.find(".")) as String;
        var body = { "entity_id" => entityId } as Dictionary;
        var keys = data.keys();
        for (var i = 0; i < keys.size(); i++) {
            body[keys[i]] = data[keys[i]];
        }
        Communications.makeWebRequest(
            baseUrl() + "/api/services/" + domain + "/" + service,
            body,
            {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :headers => headers(),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            cb
        );
    }

    // Works for both number.* and input_number.* entities.
    function setNumber(entityId as String, value as Number, cb as Method) as Void {
        var domain = entityId.substring(0, entityId.find(".")) as String;
        Communications.makeWebRequest(
            baseUrl() + "/api/services/" + domain + "/set_value",
            { "entity_id" => entityId, "value" => value },
            {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :headers => headers(),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            cb
        );
    }
}
