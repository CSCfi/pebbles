app.controller('InitializationController', ['$scope', '$location', 'Restangular', function($scope, $location, Restangular) {
    var initialize = Restangular.all('initialize');
    var initialized = false;

    $scope.initialize_user = function() {
        var params = { email: $scope.user.email,
                       password: $scope.user.password};
        initialize.post(params).then(function(response) {
            $location.path("/");
        }, function(response) {
            initialized = true;
        });
    };

    $scope.isInitialized = function() {
        return initialized;
    };
}]);
