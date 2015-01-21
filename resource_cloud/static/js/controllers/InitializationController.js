app.controller('InitializationController', ['$scope', '$location', 'Restangular', function($scope, $location, Restangular) {
    var initialize = Restangular.all('initialize');
    var initialized = false;

    $scope.initialize_user = function() {
        var params = { email: $scope.email,
                       password: $scope.password};
        if ($scope.verify == $scope.password) {
            initialize.post(params).then(function(response) {
                $location.path("/");
            }, function(response) {
                initialized = true;
            });
        } else {
            console.log("passwords did not match");
        }
    };

    $scope.isInitialized = function() {
        return initialized;
    };
}]);
