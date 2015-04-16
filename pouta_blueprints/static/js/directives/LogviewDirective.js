// create a custom directive for displaying instance lifetime in human readable format
app.directive('logview', ["$http", "AuthService", function ($http, AuthService) {
    function link(scope, element, attributes) {

        var logUrl = attributes['url'];
        var nLines = attributes['nlines'];

        $http(
            {
                method: "GET",
                url: logUrl,
                headers: {
                    token: AuthService.getToken(),
                    Authorization: "Basic " + AuthService.getToken()
                }
            }
        ).success(function (data, status, headers, config) {

                var idx = data.length - 1;
                var nLfs = 0;
                while (idx >= 0) {
                    if (data[idx] == '\n') {
                        nLfs += 1;
                    }

                    if (nLfs > nLines) {
                        break;
                    }
                    idx -= 1;
                }

                element.text(data.slice(idx+1));
            }
        );

    }
    return {
        restrict: 'E',
        link: link
    };
}]);
