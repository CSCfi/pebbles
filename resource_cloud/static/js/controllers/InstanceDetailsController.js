app.controller('InstanceDetailsController', ['$q', '$http', '$routeParams', '$scope', '$interval', 'AuthService', 'Restangular',
    function ($q, $http, $routeParams, $scope, $interval, AuthService, Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var instance_id = $routeParams.instance_id;
        var instance;
        Restangular.one('provisioned_resources', instance_id).get().then(function (response) {
            instance = response;
            $scope.instance = response;
        }).then(function () {
            Restangular.one('resources', instance.resource_id).get().then(function (response) {
                $scope.service = response;
            });
        });

        $scope.refreshLogs = function (instance) {
            if (!instance.logs.length) {
                Restangular.one('provisioned_resources', instance.id).get().then(function (response) {
                    instance = response;
                    $scope.instance = instance;
                });
            }
            for (var i = 0; i < instance.logs.length; i++) {
                $http(
                    {
                        method: "GET",
                        url: instance.logs[i].url,
                        log_type: instance.logs[i].type,
                        headers: {
                            token: AuthService.getToken(),
                            Authorization: "Basic " + AuthService.getToken()
                        }
                    }
                ).success(function (data, status, headers, config) {
                        var log_type = config['log_type'];
                        if (!$scope.logs)
                            $scope.logs = [];
                        $scope.logs[log_type] = data;
                    }
                );
            }
        };

    }
])
;
