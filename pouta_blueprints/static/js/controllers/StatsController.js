app.controller('StatsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        var stats = Restangular.all('stats');

        stats.getList().then(function (response) {
            $scope.stats = response[0];
        });
/*
        $scope.selectBlueprint = function(blueprint) {
            $scope.selectedBlueprint = blueprint;
            $scope.$broadcast('schemaFormRedraw');
        };

        $scope.activate = function (blueprint) {
            blueprint.is_enabled = true;
            blueprint.put();
        };
*/
    }]);
