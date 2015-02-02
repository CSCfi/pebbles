app.controller('ActivationController', ['$scope', '$routeParams', '$location', 'Restangular', function($scope, $routeParams, $location, Restangular) {
    var activations = Restangular.all('activations');
    $scope.activate_user = function() {
        var token = $routeParams.token;
        activations.post({token: token,
                          password: $scope.password});
    };
}]);
