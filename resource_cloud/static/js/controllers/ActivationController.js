app.controller('ActivationController', ['$scope', '$routeParams', '$location', 'Restangular', function($scope, $routeParams, $location, Restangular) {
    var activations = Restangular.all('activations');
    var activationSuccess = false;

    $scope.activate_user = function() {
        var token = $routeParams.token;
        activations.post({token: token, password: $scope.password}).then(function(resp) {
            activationSuccess = true;
        });
    };

    $scope.activationSuccess = function() {
        return activationSuccess;
    }

}]);
